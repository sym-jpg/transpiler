var g_1: VArray<Int32, $3> = [1, 2, 3]

func func_1(): Int32 {
  var i: Int32 = 0
  while ((i < 3)) {
    g_1[Int64(i)] = cInt32Add(g_1[Int64(i)], i)
    i = cInt32Add(i, 1)
  }
  return g_1[Int64(2)]
}

