// ODIN provisional adjustable fixture base. Units: mm.
// Camera-specific carriers, PCB hole patterns and tripod interface are pending measurements.
// This is not a fit-validated complete camera mount.
plate_width = 80;
plate_depth = 40;
plate_thickness = 3;
corner_radius = 3;
slot_length = 12;   // overall capsule length
slot_width = 3.2;
slot_x = plate_width / 2 - 14;
slot_y = plate_depth / 2 - 8;
$fn = 48;

assert(plate_thickness > 0);
assert(corner_radius > 0 && 2 * corner_radius < min(plate_width, plate_depth));
assert(slot_length > slot_width && slot_width > 0);
assert(slot_x > slot_length && slot_y > slot_width);
assert(slot_x + slot_length / 2 < plate_width / 2 - corner_radius);
assert(slot_y + slot_width / 2 < plate_depth / 2 - corner_radius);

module capsule(length, width) {
    hull() {
        translate([-(length-width)/2, 0]) circle(d=width);
        translate([(length-width)/2, 0]) circle(d=width);
    }
}

linear_extrude(height=plate_thickness)
difference() {
    offset(r=corner_radius)
        square([plate_width - 2*corner_radius, plate_depth - 2*corner_radius], center=true);
    for (x = [-slot_x, 0, slot_x])
        for (y = [-slot_y, slot_y])
            translate([x, y]) capsule(slot_length, slot_width);
}
