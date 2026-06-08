var g_1: VArray<VArray<Int32, $2>, $2> = [[1, 2], [3, 4]]

func func_1(): Int32 {
  var __c_assign_tmp_0 = g_1[Int64(1)]
  __c_assign_tmp_0[Int64(0)] = cInt32Add(g_1[Int64(0)][Int64(1)], 1)
  g_1[Int64(1)] = __c_assign_tmp_0
  return g_1[Int64(1)][Int64(0)]
}

