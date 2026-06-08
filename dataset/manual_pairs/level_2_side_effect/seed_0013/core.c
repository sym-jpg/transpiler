int g_1 = 0;

int func_1(void)
{
    int l_1 = 1;
    l_1 = (g_1 = l_1 + 2, g_1 + 3);
    g_1 = l_1;
    return g_1;
}
