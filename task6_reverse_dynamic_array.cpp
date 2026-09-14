// Task 6 - reversing a dynamic array in the same array
#include <iostream>
using namespace std;

void printArray(int* arr, int n)
{
    for (int* p = arr; p < arr + n; p++)
    {
        cout << *p << " ";
    }
    cout << endl;
}

int main()
{
    int n;
    cout << "Enter size of array: ";
    cin >> n;

    if (n <= 0)
    {
        cout << "Size should be more than 0." << endl;
        return 0;
    }

    int* arr = new int[n];

    cout << "Enter " << n << " elements:\n";
    for (int* p = arr; p < arr + n; p++)
    {
        cin >> *p;
    }

    cout << "\nOriginal array: ";
    printArray(arr, n);

    // one pointer at the start, one at the end
    // swap them and move both towards the middle
    int* left = arr;
    int* right = arr + n - 1;

    while (left < right)
    {
        int temp = *left;
        *left = *right;
        *right = temp;

        left++;
        right--;
    }

    cout << "Reversed array: ";
    printArray(arr, n);

    delete[] arr;
    arr = nullptr;

    return 0;
}
