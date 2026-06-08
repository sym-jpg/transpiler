int g_1 = 7;
unsigned int g_2 = 3U;

int func_1(void)
{
    int l_1 = (int)g_2;
    if ((g_1 > l_1) || (g_2 == 0U))
    {
        l_1 = g_1 - l_1;
    }
    return l_1;
}
