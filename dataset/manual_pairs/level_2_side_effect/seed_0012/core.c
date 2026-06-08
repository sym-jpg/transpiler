int g_1 = 1;
int g_2 = 4;

int func_1(void)
{
    int l_1 = 0;
    if ((g_1 = g_1 + 1) && (g_2 = g_2 - 1))
    {
        l_1 = g_1 + g_2;
    }
    return l_1;
}
