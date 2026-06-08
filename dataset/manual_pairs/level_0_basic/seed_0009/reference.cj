var g_1: Int32 = 0
var g_2: UInt32 = 0u32

func func_1(): Int32 {
  var l_1: Int32 = 0
  var l_2: UInt32 = 0u32
  l_1 = cInt32Add(g_1, 5)
  l_2 = cUInt32Add(g_2, 1u32)
  return cInt32Add(l_1, Int32(l_2))
}
