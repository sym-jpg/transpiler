var g_1: UInt32 = 1u32
var g_2: Int32 = -2

func func_1(): Int32 {
  var l_1: Int32 = Int32(g_1)
  l_1 = cInt32Sub(0, l_1)
  if ((g_2 == 0)) {
    l_1 = cInt32Add(l_1, 1)
  }
  return l_1
}

