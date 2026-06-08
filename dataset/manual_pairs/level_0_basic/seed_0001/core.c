int g_1 = 1;
unsigned int g_2 = 2U;

int func_1(void)
{
    int l_1 = 3;
    if (g_1 != 0)
    {
        g_1 = l_1 + g_1;
    }
    else
    {
        g_1 = l_1 - g_1;
    }
    g_2 = g_2 + 1U;
    return g_1;
}

