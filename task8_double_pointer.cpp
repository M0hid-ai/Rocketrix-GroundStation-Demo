// Task 8 - pointer to a pointer
#include <iostream>
using namespace std;

int main()
{
    int* p = new int;   // p points to an int on the heap
    int** pp = &p;      // pp points to p itself

    cout << "Enter a value: ";
    cin >> *p;

    cout << "\nValue using single pointer (*p): " << *p << endl;
    cout << "Value using double pointer (**pp): " << **pp << endl;

    // just to see what each one holds
    cout << "\nAddress of the int (p): " << p << endl;
    cout << "Address of p (pp): " << pp << endl;
    cout << "What pp points to (*pp): " << *pp << endl;

    int newVal;
    cout << "\nEnter a new value (will be changed using double pointer): ";
    cin >> newVal;
    **pp = newVal;   // two stars to reach the actual int

    cout << "Updated value using *p: " << *p << endl;
    cout << "Updated value using **pp: " << **pp << endl;

    delete p;
    p = nullptr;   // pp still points to p, and p is now nullptr

    cout << "\nMemory released." << endl;

    return 0;
}
