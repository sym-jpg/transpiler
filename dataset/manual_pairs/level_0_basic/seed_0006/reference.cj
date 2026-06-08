var g_1: Int32 = 0
var g_2: UInt32 = 0u32
var g_3: VArray<Int32, $2> = [0, 0]

func func_1(): Int32 {
  var l_1: Int32 = 0
  var l_2: UInt32 = 0u32
  var l_3: VArray<Int32, $2> = [0, 0]
  l_1 = g_1
  l_2 = g_2
  l_3[Int64(0)] = l_1
  return l_3[Int64(0)]
}

