var g_1: Int32 = 7
var g_2: UInt32 = 3u32

func func_1(): Int32 {
  var l_1: Int32 = Int32(g_2)
  if (((g_1 > l_1) || (g_2 == 0u32))) {
    l_1 = cInt32Sub(g_1, l_1)
  }
  return l_1
}
