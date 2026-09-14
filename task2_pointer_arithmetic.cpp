// Task 2 - going through an array with a pointer (no arr[i])
#include <iostream>
using namespace std;

int main()
{
    const int SIZE = 10;
    int arr[SIZE];
    int* p = arr;   // array name already points to first element

    cout << "Enter " << SIZE << " numbers:\n";
    for (int i = 0; i < SIZE; i++)
    {
        cout << "Element " << i + 1 << ": ";
        cin >> *(p + i);
    }

    cout << "\nElements and their addresses:\n";
    for (int i = 0; i < SIZE; i++)
    {
        cout << "Value: " << *(p + i) << "\tAddress: " << (p + i) << endl;
    }

    // start max and min from the first element
    int sum = 0;
    int largest = *p;
    int smallest = *p;

    // walk the pointer from start till it reaches the end
    for (int* q = arr; q < arr + SIZE; q++)
    {
        sum += *q;
        if (*q > largest)
            largest = *q;
        if (*q < smallest)
            smallest = *q;
    }

    cout << "\nSum: " << sum << endl;
    cout << "Largest: " << largest << endl;
    cout << "Smallest: " << smallest << endl;

    return 0;
}
