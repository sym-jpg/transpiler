var g_1: Int32 = 1
var g_2: UInt32 = 2u32

func func_1(): Int32 {
  var l_1: Int32 = 3
  if (g_1 != 0) {
    g_1 = cInt32Add(l_1, g_1)
  } else {
    g_1 = cInt32Sub(l_1, g_1)
  }
  g_2 = cUInt32Add(g_2, 1u32)
  return g_1
}

