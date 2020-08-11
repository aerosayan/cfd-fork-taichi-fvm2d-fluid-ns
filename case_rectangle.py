#========================================
# Supersonic Shockwave Wedge Test Case
#
# @author hejob.moyase@gmail.com
#========================================

import taichi as ti
from solver.Solver import Solver
import time

##################
# TODO: is multiple taichi instance ok?
real = ti.f32
# ti.init(arch=ti.cpu, default_fp=real, kernel_profiler=True)

width = 2.0
height = 0.4
ni = 200
nj = 40

@ti.kernel
def generate_grids(
        x: ti.template(), i0: ti.i32, i1: ti.i32, j0: ti.i32, j1: ti.i32):
    ## EXAMPLE: supersonic wedge
    ## NOTICE: virtual voxels are also generated here
    ## TODO: generate bc by program?
    dx = width / ni
    dy = height / nj
    for I in ti.grouped(ti.ndrange((i0, i1), (j0, j1))):
        tx = dx * I[0]
        ty = dy * I[1]
        px = tx
        py = ty
        x[I] = ti.Vector([px, py])

##################
# Main Test Case
##################
if __name__ == '__main__':

    ### initialize solver with simulation settings
    gamma = 1.4
    ma0 = 0.3
    # re0 = 1.225 * (ma0 * 343) * 1.0 / (1.81e-5)
    re0 = 1e+4
    p0 = 1.0 / gamma / ma0 / ma0
    e0 = p0 / (gamma - 1.0) + 0.5 * 1.0

    solver = Solver(
        width=width,
        height=height,
        ni=ni,
        nj=nj,
        ma0=ma0,
        dt=1e-5,
        is_viscous=True,
        temp0_raw=273,
        re0=re0,
        display_field=True,
        display_value_min=0.0,
        display_value_max=2.0,
        display_scale=10,
        output_line=True,
        output_line_ends=((1.4, 0.02), (1.4, 0.38)),
        output_line_num_points=40,
        output_line_var=1,  # Mach number. 0~7: rho/u/v/et/uu/p/a/ma
        output_line_plot_var=1)  # output along x-axis on plot

    ### generate grids in Solver's x tensor
    (i_range, j_range) = solver.range_grid
    generate_grids(solver.x, i_range[0], i_range[1], j_range[0], j_range[1])

    ### boundary conditions
    ###     0/1/2/3/4: inlet(super)/outlet(super)/symmetry/wall(noslip)/wall(slip)
    i_bc = int(0.2 * ni // 1) + 1

    bc_q_values=[
        (1.0, 1.0 * 1.0, 1.0 * 0.0, 1.0 * e0)
    ]

    bc_array = [
        (10, 1, nj + 1, 0, 0, 0),         # left subsonic inlet
        (11, 1, nj + 1, 0, 1, 0),         # right, subsonic outlet
        (3, 1, ni + 1, 1, 0, None),       # down, wall
        (3, 1, ni + 1, 1, 1, None),       # up, wall
        # (2, 1, ni + 1, 1, 0, None),     # down, sym
        # (2, 1, ni + 1, 1, 1, None),     # up, sym
    ]
    solver.set_bc(bc_array, bc_q_values)

    solver.set_display_options(
            display_show_grid=False,
            display_show_xc=False,
            display_show_velocity=True,
            display_show_velocity_skip=(4, 2),
            display_show_surface=False,
            display_show_surface_norm=False
        )

    ### start simulation loop
    t = time.time()
    solver.run()

    ### output statistics
    print(f'Solver time: {time.time() - t:.3f}s')
    ti.kernel_profiler_print()
    ti.core.print_profile_info()
    ti.core.print_stat()