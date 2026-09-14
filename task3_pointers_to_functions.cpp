// Task 3 - sending addresses to functions
#include <iostream>
using namespace std;

// gets sum and difference, results go back through the last two pointers
void sumAndDiff(int* a, int* b, int* sum, int* diff)
{
    *sum = *a + *b;
    *diff = *a - *b;
}

// swaps the actual variables in main, not copies
void swapValues(int* a, int* b)
{
    int temp = *a;
    *a = *b;
    *b = temp;
}

int main()
{
    int x, y;
    int sum, diff;

    cout << "Enter first number: ";
    cin >> x;
    cout << "Enter second number: ";
    cin >> y;

    cout << "\nBefore operations:\n";
    cout << "x = " << x << ", y = " << y << endl;

    sumAndDiff(&x, &y, &sum, &diff);
    cout << "\nSum = " << sum << endl;
    cout << "Difference (x - y) = " << diff << endl;

    swapValues(&x, &y);
    cout << "\nAfter swapping:\n";
    cout << "x = " << x << ", y = " << y << endl;

    return 0;
}
