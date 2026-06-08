int g_1 = 0;

int func_2(int x)
{
    return x + 1;
}

int func_1(void)
{
    g_1 = func_2(g_1);
    func_2(g_1);
    return g_1;
}

