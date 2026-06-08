var g_1: VArray<VArray<Int32, $2>, $2> = [[1, 2], [3, 4]]

func func_1(): Int32 {
  var i: Int32 = 0
  while ((i < 2)) {
    g_1[Int64(i)][1] = cInt32Add(g_1[Int64(i)][0], g_1[Int64(i)][1])
    i = cInt32Add(i, 1)
  }
  return g_1[1][1]
}
