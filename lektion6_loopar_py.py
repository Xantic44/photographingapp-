"""Simple loop examples for beginners.

This file demonstrates `for` and `while` loops in Python
with clear, beginner-friendly comments and short demo functions.
Run the file to see the example outputs.
"""

def demo_for_loops():
    # 1) Iterate over a list of items
    fruits = ["apple", "banana", "cherry"]
    print("For loop: iterate over a list")
    for fruit in fruits:
        # `fruit` refers to the current element in the list
        print(" -", fruit)

    # 2) Use range() to iterate by index or count
    print("\nFor loop: using range() to iterate numbers")
    for index in range(1, 6):
        # index goes 1,2,3,4,5
        print("Number:", index)

    # 3) enumerate() gives both index and value
    print("\nFor loop: enumerate() to get index and value")
    for index, fruit in enumerate(fruits, start=1):
        print(index, "->", fruit)

    # 4) Nested for loops (useful for grids or pairs)
    print("\nNested for loops: rows x cols")
    rows = 2
    cols = 3
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            print(f"({row},{col})", end=" ")
        print()  # newline after each row

    # 5) for-else: else runs when loop completes without break
    print("\nFor-else example")
    target = "banana"
    for fruit in fruits:
        if fruit == target:
            print(target, "found!")
            break
    else:
        # This else runs only if the loop did NOT encounter a break
        print(target, "not found")


def demo_while_loops():
    # 1) Simple counter-based while loop
    print("\nWhile loop: counter example")
    count = 0
    while count < 5:
        print("count =", count)
        count += 1

    # 2) While loop with break (sentinel pattern)
    print("\nWhile loop: sentinel + break")
    n = 1
    while True:
        # stop when n reaches 4
        if n == 4:
            print("Reached", n, "— breaking out")
            break
        print("n =", n)
        n += 1

    # 3) Avoid infinite loops: always ensure the condition will change
    print("\nWhile loop: avoid infinite loops (demo stops automatically)")
    times = 0
    while times < 3:
        print("looping", times)
        times += 1


def demo_break_continue():
    # break: exit the loop immediately
    print("\nbreak and continue examples")
    for num in range(1, 8):
        if num == 5:
            print("Breaking at", num)
            break
        print("->", num)

    # continue: skip the rest of this iteration
    print("\ncontinue: skip even numbers")
    for num in range(1, 8):
        if num % 2 == 0:
            continue  # skip even numbers
        print(num)


def exercises_comments():
    # Short exercise prompts (read and try to implement)
    # 1) Write a for-loop that prints the squares of numbers 1..10
    # 2) Use a while-loop to sum numbers until the sum >= 100
    # 3) Modify the nested loop above to print a multiplication table
    pass


if __name__ == "__main__":
    # Run demos so beginners can run this file directly
    demo_for_loops()
    demo_while_loops()
    demo_break_continue()
    print("\nRead the exercises in the file and try them!")

"number = 1"

"while number <= 5:"
"    print(number)"
"    number += 1 (plussar 1 varje varv/gång)"
"enkel bas loop"

"number = 1
summa = 0

while number <= 10:
    summa += number
    number += 1

print(summa)
"1,3,6 osv"

secret = 7
guess = 0

while guess != secret:
    guess = int(input("Gissa talet: "))

    if guess != secret:
        print("Fel! Försök igen.")

print("Grattis! Du gissade rätt.")" 