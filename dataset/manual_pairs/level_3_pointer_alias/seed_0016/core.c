int g_1 = 3;

int func_1(void)
{
    int l_1 = 4;
    int *p = &l_1;
    if (p != 0)
    {
        *p = *p + g_1;
    }
    return l_1;
}
