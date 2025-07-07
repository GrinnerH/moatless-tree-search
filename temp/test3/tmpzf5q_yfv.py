```python
import os

# Compile the program
os.system('g++ test3.cpp -o test3')

# Create an input file with an overflow payload
with open('input.txt', 'w') as f:
    f.write('A' * 40 + '\n')  # Overflow payload exceeds buffer1 size

# Run the program with the crafted input
os.system('./test3 input.txt')
```