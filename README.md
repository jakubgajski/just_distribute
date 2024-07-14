### Overview  
  
Haven't planned your functions for large workloads or don't feel comfortable with various options for concurrency?  
Please, don't be sad - just distribute.

### Installation  
  
```bash
pip install just-distibute
```
   
### TL;DR  
   
```python
from just_distribute import distribute

@distribute(job='compute', workers=8)  # job in ('compute', 'io', 'web', 'ray')
def your_time_consuming_func(*args):
    ...
```
  
### Getting Started  
   
Always make sure your function you want to distribute has proper typehints, because just_distribute makes some 
assumptions based on type annotations. Also, the data to be distributed shall be passed as positional arguments, 
keyword arguments are treated as constants.
  
#### CPU intensive tasks
  
Instead of:  
  
```python
def some_existing_cpu_intensive_function(x: int, y: int) -> int:
    ...

# slow, probably need to rewrite it ;(
results = []
for const1, const2 in zip(range(1000), range(4000, 2000, -2)):
    results.append(
        some_existing_cpu_intensive_function(const1, const2)    
    )
```
  
Do:  
  
```python
from just_distribute import distribute


@distribute(job='compute', workers=8)
def some_existing_cpu_intensive_function(x: int, y: int) -> int:
    ...

# <happy CPU fan noises>
results = some_existing_cpu_intensive_function(range(1000), range(4000, 2000, -2))
```  
   
<details>
<summary>Curious what happens in the background?</summary>
For the compute / processes type workload, ProcessPool from the pathos package is used to spawn given number of processes.  
The pathos package utilizes dill as the object serialization protocol, which is an enhanced variant of pickle.  
  
Roughly what happens when using ProcessPool:  
- ~~child~~of age worker processes with independent memory are spawned  
- dill is used to serialize chunks of data and the execution code  
- serialized stuff is send to workers for execution  
- after execution partial results are collected and aggregated in the parent process  
  
Why I'm not using standard library, e.g. ProcessPoolExecutor from concurrent.futures? 
Because default serialization protocol - pickle - is very... picky on what can be serialized 
and therefore send to workers, while dill is more forgiving.  
  
To read more visit e.g.:  
- [multiprocessing @ geeksforgeeks](https://www.geeksforgeeks.org/multiprocessing-python-set-1/)
- [multiprocessing @ superfastpython](https://superfastpython.com/multiprocessing-in-python/)
</details>
  
#### I/O intensive tasks
  
Instead of:  
  
```python
def some_existing_io_intensive_function(data_to_write: bytes, filename: str, verbose: bool = True):
    ...

# slow, probably need to rewrite it ;(
data_store: dict = ...  # some processed data to save
for name, data in data_store.items():
    some_existing_io_intensive_function(data, name)
```
  
Do:  
  
```python
from just_distribute import distribute


@distribute(job='io', workers=8)
def some_existing_io_intensive_function(data_to_write: bytes, filename: str, verbose: bool = True):
    ...

data_store: dict = ...  # some processed data to save
# <happy HDD noises???>
# any keyword arguments are not distributed :)
some_existing_io_intensive_function(data_store.values(), data_store.keys(), verbose=False)
```    
   
<details>
<summary>Curious what happens in the background?</summary>
For the io / threads type workload, ThreadPoolExecutor from the standard library is used.  
Intuitively, when some tasks can be executed independently of Python interpreter(e.g. by an external C++ library or by the OS), 
main program can just be busy overseeing them like the boss.   
  
Roughly what happens when using ThreadPoolExecutor:  
- within a shared memory, a number of threads is created  
- each thread (ideally) has an exclusive subset of data delegated  
- while threads are running, the parent process is constantly switching context between them, asking "already done?"  
- when all threads are done, main process can continue with whatever left to be done  
  
To read more visit e.g.:  
- [mutithreading @ geeksforgeeks](https://www.geeksforgeeks.org/multithreading-python-set-1/)  
- [what is multithreading @ clouddevs](https://clouddevs.com/python/multithreading/#11-What-is-Multithreading)
</details>
  
#### Somewhere over the network :guitar:
  
Instead of:

```python
def some_existing_web_requesting_function(data_to_send: dict, url: str, api_key: str):
    ...

# slow, probably need to rewrite it ;(
data_store: list[dict] = ...  # some data to process on a remote service
for data in data_store:
    some_existing_web_requesting_function(data, url="https://some_web_api.com/process", api_key="***")
```
  
Do:  
  
```python
from just_distribute import distribute


@distribute(job='web', workers=8)
def some_existing_web_requesting_function(data_to_send: dict, url: str, api_key: str):
    ...

data_store: list[dict] = ...  # some data to process on a remote service
# <happy router blinking>
some_existing_web_requesting_function(data_store, url="https://some_web_api.com/process", api_key="***")
```  
   
<details>
<summary>Curious what happens in the background?</summary>
For the web / coroutines type workload, asyncio from the standard library is used for concurrency.  
Async function is similar to a generator - it is an object which execution flow can be paused and resumed.  
  
Roughly what happens when using distribute decorator with io job:  
- a queue is fed with data elements  
- a number of consumers are created, so use has control on how many concurrent request may be sent  
- a single-thread event loop is spawned  
- consumer is being paused by the loop when waiting idle for the response or resumed when next piece of data can be consumed  
- when the whole queue is consumed, aggregated data is being returned  
  
To read more visit e.g.:  
- [asyncio @ docs.python](https://docs.python.org/3/library/asyncio.html)  
- [asyncio @ superfastpython](https://superfastpython.com/python-asyncio/)
</details>
  
#### Or in the existing Ray cluster  
  
Instead of:
  
```python
def some_existing_cpu_intensive_function(x: int, y: int) -> int:
    ...

# slow, probably need to rewrite it ;(
results = []
for const1, const2 in zip(range(1000), range(4000, 2000, -2)):
    results.append(
        some_existing_cpu_intensive_function(const1, const2)    
    )
```
  
Do:  
  
```python
from just_distribute import distribute


@distribute(job='ray')
def some_existing_cpu_intensive_function(x: int, y: int) -> int:
    ...

# <happy CPU fan noises on the cluster's host>
results = some_existing_cpu_intensive_function(range(1000), range(4000, 2000, -2))
```  
  
For instruction how to set up Ray cluster on bare metal or in the cloud, see: [Ray documentation](https://docs.ray.io/en/latest/cluster/vms/getting-started.html)  
   
<details>
<summary>Curious what happens in the background?</summary>
For the ray / cluster type workload, Ray Python library is used, that abstracts multiprocessing to a more general scenario.  
Instead of being constrained to the capabilities of a single machine, Ray can be scaled up to many of them.  
  
Roughly what happens when using Ray (on an already existing cluster):  
- tasks, a Ray flavor of futures (objects with a promise of having a value at some point), are send to the cluster  
- Ray automatically spawns required number of workers (number of workers is defined implicitly)  
- results are moved from workers to common object store (shared memory)  
- results can be pulled back and aggregated    
  
To read more visit e.g.:  
- [key concepts @ docs.ray](https://docs.ray.io/en/latest/ray-core/key-concepts.html)  
</details>
  
### More advanced cases  
  
When wrapped function by default takes iterable, autobatch takes care of it:  
  
```python
from just_distribute import distribute

@distribute(job='compute', workers=8, autobatch=True) # default autobatch is True, so you can just omit this parameter
def intensive_computation(numbers: list[int]):
    ...

a: list[int] = ...
intensive_computation(a)  # works fine
```
  
When wrapped function by default takes equal length iterables:  

```python
from just_distribute import distribute

@distribute(job='compute', workers=8, autobatch=False)  # default autobatch is True
def intensive_computation(numbers1: list[int], numbers2: list[int]):
    for n1, n2 in zip(numbers1, numbers2):
        ...

a: list[int] = ...
b: list[int] = ...
intensive_computation(a, b)  # TypeError: 'int' object is not iterable -> because autobatch is off 
# and wrapped function takes iterables as an input

# manually batched
a: list[list[int]] = ...
b: list[list[int]] = ...
assert len(a) == len(b)  # True
assert all([len(_a) == len(_b) for _a, _b in zip(a, b)])  # True -> properly, manually batched data
intensive_computation(a, b)  # works fine

# or just use default autobatch=True
a: list[int] = ...
b: list[int] = ...
intensive_computation(a, b)  # works fine
```  
  
When wrapped function by default takes possibly different length iterables:  
  
```python
from just_distribute import distribute
from itertools import product

@distribute(job='compute', workers=8, autobatch=False)  # default autobatch is True
def intensive_computation(numbers1: list[int], numbers2: list[int]):
    for n1, n2 in product(numbers1, numbers2):
        ...

# manually batched    
a: list[list[int]] = ...
b: list[list[int]] = ...
intensive_computation(a, b)  # works fine

# or autobatch=True
a: list[int] = ...
b: list[int] = ...
intensive_computation(a, numbers2=b)  # works fine in this certain example, because autobatch takes care of numbers1 
# and numbers2 is treated as a constant
```  
  
When wrapped function has mixed type, non-constant (in distribute sense) parameters:  
  
```python
from just_distribute import distribute
from collections.abc import Iterable

@distribute(job='compute', workers=8)
def intensive_computation(numbers: list[int], power: int, verbose: bool = True):
    ...    

a = list(range(1000)) * 100
b = range(100)
assert len(a) > len(b)
assert len(a) % len(b) == 0  # for every element in b there is N elements in a
intensive_computation(a, b, verbose=False)  # works fine

# or autobatch=False and data manually batched
a: list[list[int]] = ...
b: list[int] = ...
intensive_computation(a, b, verbose=False)  # works fine
```