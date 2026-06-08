int g_1 = 1;
int g_2 = 2;

int func_1(void)
{
    int l_1 = 0;
    l_1 = (g_1 = g_1 + 1, g_2 + g_1);
    if ((g_1 != 0) && (g_2 != 0))
    {
        g_2 = l_1;
    }
    return g_2;
}

