// Task 5 - dynamic array, all work done with pointers
#include <iostream>
using namespace std;

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

    int sum = 0, evenCount = 0, oddCount = 0;
    int largest = *arr;
    int smallest = *arr;

    cout << "\nElements: ";
    for (int* p = arr; p < arr + n; p++)
    {
        cout << *p << " ";

        sum += *p;

        if (*p % 2 == 0)
            evenCount++;
        else
            oddCount++;

        if (*p > largest)
            largest = *p;
        if (*p < smallest)
            smallest = *p;
    }

    // cast to double so average doesnt cut off the decimal part
    double avg = (double)sum / n;

    cout << "\n\nSum: " << sum << endl;
    cout << "Average: " << avg << endl;
    cout << "Even numbers: " << evenCount << endl;
    cout << "Odd numbers: " << oddCount << endl;
    cout << "Largest: " << largest << endl;
    cout << "Smallest: " << smallest << endl;

    delete[] arr;
    arr = nullptr;

    return 0;
}
