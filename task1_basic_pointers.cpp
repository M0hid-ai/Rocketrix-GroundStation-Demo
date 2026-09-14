// Task 1 - Basic pointer stuff
#include <iostream>
using namespace std;

int main()
{
    int num;
    int* ptr = &num;   // ptr now holds the address of num

    cout << "Enter an integer: ";
    cin >> num;

    cout << "\nValue of num: " << num << endl;
    cout << "Address of num (&num): " << &num << endl;
    cout << "Address stored in ptr: " << ptr << endl;
    cout << "Value using *ptr: " << *ptr << endl;

    // changing num without touching num directly, just through ptr
    int newVal;
    cout << "\nEnter a new value to put through the pointer: ";
    cin >> newVal;
    *ptr = newVal;

    cout << "Updated value of num: " << num << endl;
    cout << "Updated value using *ptr: " << *ptr << endl;

    return 0;
}
