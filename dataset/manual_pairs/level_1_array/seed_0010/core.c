int g_1[2][2] = {{1, 2}, {3, 4}};

int func_1(void)
{
    int i = 0;
    while (i < 2)
    {
        g_1[i][1] = g_1[i][0] + g_1[i][1];
        i = i + 1;
    }
    return g_1[1][1];
}
