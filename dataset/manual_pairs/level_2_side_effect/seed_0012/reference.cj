var g_1: Int32 = 1
var g_2: Int32 = 4

func func_1(): Int32 {
  var l_1: Int32 = 0
  g_1 = cInt32Add(g_1, 1)
  if ((g_1 != 0)) {
    g_2 = cInt32Sub(g_2, 1)
    if ((g_2 != 0)) {
      l_1 = cInt32Add(g_1, g_2)
    }
  }
  return l_1
}
