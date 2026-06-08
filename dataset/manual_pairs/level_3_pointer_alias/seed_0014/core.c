int g_1 = 1;

int func_1(void)
{
    int *p = &g_1;
    *p = *p + 5;
    return g_1;
}
