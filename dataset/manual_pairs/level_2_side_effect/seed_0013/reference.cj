var g_1: Int32 = 0

func func_1(): Int32 {
  var l_1: Int32 = 1
  g_1 = cInt32Add(l_1, 2)
  l_1 = cInt32Add(g_1, 3)
  g_1 = l_1
  return g_1
}
