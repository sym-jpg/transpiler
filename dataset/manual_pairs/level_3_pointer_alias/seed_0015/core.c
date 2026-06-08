int g_1 = 1;
int g_2 = 2;

int func_1(void)
{
    int *p = &g_1;
    *p = 7;
    p = &g_2;
    *p = g_1 + g_2;
    return g_2;
}
