unsigned int g_1 = 1U;
int g_2 = -2;

int func_1(void)
{
    int l_1 = (int)g_1;
    l_1 = -l_1;
    if (!g_2)
    {
        l_1 = l_1 + 1;
    }
    return l_1;
}

