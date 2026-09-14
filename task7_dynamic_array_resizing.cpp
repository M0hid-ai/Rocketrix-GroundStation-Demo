// Task 7 - array that grows when it gets full
#include <iostream>
using namespace std;

int main()
{
    int capacity = 3;
    int size = 0;
    int* arr = new int[capacity];

    int count;
    cout << "How many elements do you want to enter? ";
    cin >> count;

    for (int i = 0; i < count; i++)
    {
        // no space left, so make a bigger array
        if (size == capacity)
        {
            int newCapacity = capacity * 2;
            int* temp = new int[newCapacity];

            // copy old values into the new one
            for (int j = 0; j < size; j++)
            {
                *(temp + j) = *(arr + j);
            }

            delete[] arr;   // old one not needed anymore
            arr = temp;
            capacity = newCapacity;

            cout << "  (array was full, capacity increased to " << capacity << ")\n";
        }

        cout << "Enter element " << i + 1 << ": ";
        cin >> *(arr + size);
        size++;
    }

    cout << "\nAll elements: ";
    for (int* p = arr; p < arr + size; p++)
    {
        cout << *p << " ";
    }

    cout << "\nFinal size: " << size << endl;
    cout << "Final capacity: " << capacity << endl;

    delete[] arr;
    arr = nullptr;

    return 0;
}
