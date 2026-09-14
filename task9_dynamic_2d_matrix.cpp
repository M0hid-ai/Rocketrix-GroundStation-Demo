// Task 9 - 2D matrix made with int**
#include <iostream>
using namespace std;

int main()
{
    int rows, cols;
    cout << "Enter number of rows: ";
    cin >> rows;
    cout << "Enter number of columns: ";
    cin >> cols;

    if (rows <= 0 || cols <= 0)
    {
        cout << "Rows and columns should be more than 0." << endl;
        return 0;
    }

    // first make an array of row pointers, then give each row its own array
    int** matrix = new int*[rows];
    for (int i = 0; i < rows; i++)
    {
        matrix[i] = new int[cols];
    }

    cout << "Enter matrix elements:\n";
    for (int i = 0; i < rows; i++)
    {
        for (int j = 0; j < cols; j++)
        {
            cout << "[" << i << "][" << j << "]: ";
            cin >> matrix[i][j];
        }
    }

    cout << "\nMatrix:\n";
    for (int i = 0; i < rows; i++)
    {
        for (int j = 0; j < cols; j++)
        {
            cout << matrix[i][j] << "\t";
        }
        cout << endl;
    }

    int sum = 0;
    int largest = matrix[0][0];
    int smallest = matrix[0][0];

    for (int i = 0; i < rows; i++)
    {
        for (int j = 0; j < cols; j++)
        {
            sum += matrix[i][j];
            if (matrix[i][j] > largest)
                largest = matrix[i][j];
            if (matrix[i][j] < smallest)
                smallest = matrix[i][j];
        }
    }

    cout << "\nSum: " << sum << endl;
    cout << "Largest: " << largest << endl;
    cout << "Smallest: " << smallest << endl;

    // delete rows first, then the array that was holding them
    for (int i = 0; i < rows; i++)
    {
        delete[] matrix[i];
    }
    delete[] matrix;
    matrix = nullptr;

    return 0;
}
