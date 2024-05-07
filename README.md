### Overview  
  
Haven't planned your functions for large workloads or don't feel comfortable with various options of concurrency?  
Please, don't be sad - just distribute.

### Installation  
  
```bash
pip install just-distibute
```
  
### Getting Started  
  
#### CPU intensive tasks
  
Instead of:  
  
```python
def some_existing_cpu_intensive_function(x: int):
    ...

# slow, probably need to rewrite it :cry:
results = []
for const in range(1000):
    results.append(
        some_existing_cpu_intensive_function(const)    
    )
```
  
Do:  
  
```python
from just_distribute import distribute


@distribute(job='compute', workers=8)
def some_existing_cpu_intensive_function(x: int) -> int:
    ...

# <happy CPU fan noises>
results = some_existing_cpu_intensive_function(range(1000))
```
  
#### I/O intensive tasks
  
Instead of:  
  
```python
def some_existing_io_intensive_function(data_to_write: bytes, filename: str, verbose: bool = False):
    ...

# slow, probably need to rewrite it :cry:
data_store = ...  # some processed data to save
for name, data in data_store.items():
    some_existing_io_intensive_function(data, name)
```
  
Do:  
  
```python
from just_distribute import distribute


@distribute(job='io', workers=8)
def some_existing_io_intensive_function(data_to_write: bytes, filename: str):
    ...

data_store = ...  # some processed data to save
# <happy HDD noises???>
some_existing_io_intensive_function(data_store.values(), data_store.keys())
```