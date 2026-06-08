var g_1: VArray<UInt32, $3> = [1u32, 2u32, 3u32]

func func_1(): Int32 {
  var i: Int32 = 0
  var acc: UInt32 = 0u32
  while ((i < 3)) {
    acc = cUInt32Add(acc, g_1[Int64(i)])
    i = cInt32Add(i, 1)
  }
  return Int32(acc)
}
