var g_1: Int32 = 0

func func_2(x: Int32): Int32 {
  return cInt32Add(x, 1)
}

func func_1(): Int32 {
  g_1 = func_2(g_1)
  func_2(g_1)
  return g_1
}

