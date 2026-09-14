// Task 10 - matrix with row/col sums, diagonals and safe cleanup
#include <iostream>
using namespace std;

int main()
{
    int rows, cols;

    // keep asking until we get proper dimensions
    cout << "Enter number of rows: ";
    cin >> rows;
    while (cin.fail() || rows <= 0)
    {
        cin.clear();
        cin.ignore(1000, '\n');
        cout << "Invalid rows, enter a number more than 0: ";
        cin >> rows;
    }

    cout << "Enter number of columns: ";
    cin >> cols;
    while (cin.fail() || cols <= 0)
    {
        cin.clear();
        cin.ignore(1000, '\n');
        cout << "Invalid columns, enter a number more than 0: ";
        cin >> cols;
    }

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

    // for a 1x1 matrix there's only one number so say it straight away
    if (rows == 1 && cols == 1)
    {
        cout << "\nThis is a 1 x 1 matrix, only one element: " << matrix[0][0] << endl;
        cout << "So row sum, column sum, min, max and both diagonals are all " << matrix[0][0] << endl;
    }

    cout << "\nRow sums:\n";
    for (int i = 0; i < rows; i++)
    {
        int rowSum = 0;
        for (int j = 0; j < cols; j++)
        {
            rowSum += matrix[i][j];
        }
        cout << "Row " << i + 1 << ": " << rowSum << endl;
    }

    cout << "\nColumn sums:\n";
    for (int j = 0; j < cols; j++)
    {
        int colSum = 0;
        for (int i = 0; i < rows; i++)
        {
            colSum += matrix[i][j];
        }
        cout << "Column " << j + 1 << ": " << colSum << endl;
    }

    int minVal = matrix[0][0];
    int maxVal = matrix[0][0];
    for (int i = 0; i < rows; i++)
    {
        for (int j = 0; j < cols; j++)
        {
            if (matrix[i][j] < minVal)
                minVal = matrix[i][j];
            if (matrix[i][j] > maxVal)
                maxVal = matrix[i][j];
        }
    }
    cout << "\nMinimum value: " << minVal << endl;
    cout << "Maximum value: " << maxVal << endl;

    // diagonals only make sense when rows == cols
    if (rows == cols)
    {
        int mainDiag = 0, secondDiag = 0;
        for (int i = 0; i < rows; i++)
        {
            mainDiag += matrix[i][i];              // top-left to bottom-right
            secondDiag += matrix[i][cols - 1 - i]; // top-right to bottom-left
        }
        cout << "\nMain diagonal sum: " << mainDiag << endl;
        cout << "Secondary diagonal sum: " << secondDiag << endl;
    }
    else
    {
        cout << "\nNot a square matrix, so no diagonal sums." << endl;
    }

    // free each row, then the row pointer array, then null it
    for (int i = 0; i < rows; i++)
    {
        delete[] matrix[i];
        matrix[i] = nullptr;
    }
    delete[] matrix;
    matrix = nullptr;

    cout << "\nAll memory freed." << endl;

    return 0;
}
