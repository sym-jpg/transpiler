int g_1[3] = {1, 2, 3};

int func_1(void)
{
    int i = 0;
    while (i < 3)
    {
        g_1[i] = g_1[i] + i;
        i = i + 1;
    }
    return g_1[2];
}

