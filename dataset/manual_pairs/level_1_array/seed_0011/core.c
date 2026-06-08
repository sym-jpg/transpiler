unsigned int g_1[3] = {1U, 2U, 3U};

int func_1(void)
{
    int i = 0;
    unsigned int acc = 0U;
    while (i < 3)
    {
        acc = acc + g_1[i];
        i = i + 1;
    }
    return (int)acc;
}
