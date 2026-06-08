var g_1: Int32 = 1
var g_2: Int32 = 2

func func_1(): Int32 {
  var l_1: Int32 = 0
  g_1 = cInt32Add(g_1, 1)
  l_1 = cInt32Add(g_2, g_1)
  if (((g_1 != 0) && (g_2 != 0))) {
    g_2 = l_1
  }
  return g_2
}

