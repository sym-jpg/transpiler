int g_1;
unsigned int g_2;

int func_1(void)
{
    int l_1;
    unsigned int l_2;
    l_1 = g_1 + 5;
    l_2 = g_2 + 1U;
    return l_1 + (int)l_2;
}
