// Task 4 - one int on the heap using new
#include <iostream>
using namespace std;

int main()
{
    int* p = new int;   // memory for one int

    cout << "Enter a value: ";
    cin >> *p;

    cout << "Value stored: " << *p << endl;

    *p = *p * 3;
    cout << "Value after multiplying by 3: " << *p << endl;

    // free it and dont leave p pointing to old memory
    delete p;
    p = nullptr;

    cout << "Memory released, pointer set to nullptr." << endl;

    return 0;
}
