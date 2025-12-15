fn add(a: i32, b: i32) -> i32 {
    var c: i32 = a + b;
    return c;
}

fn main() -> i32 {
    var x: i32 = 1;
    var y: i32 = 2;
    var z: i32 = add ( x , y );
    return 0;
}