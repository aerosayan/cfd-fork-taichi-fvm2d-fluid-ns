# ==============================================
#  structured 2D compressible FVM fluid solver
#  Multiblock solver
#  (utilises Solver class for one-block solving)
#
#  @author hejob.moyase@gmail.com
# ==============================================

import taichi as ti
import time

real = ti.f32
### main taichi init here
ti.init(arch=ti.cpu, default_fp=real, kernel_profiler=True)


@ti.data_oriented
class MultiBlockSolver:

    ################
    # constructor: block solver and drawer classes are assigned by user (allow to write custom solver and drawer classes)
    def __init__(
            self,
            BlockSolver,
            Drawer,
            ### gemotry
            width,
            height,
            ### block definitions
            n_blocks,
            block_dimensions,  # [(ni, nj)]
            # physics
            ma0,
            # simulation
            dt,
            is_dual_time=False,
            # method
            convect_method=1,  # 0~1, van Leer/Roe
            # viscous
            is_viscous=False,
            temp0_raw=273,
            re0=1e5,
            ### display
            gui_size=(400, 400),
            display_field=True,
            display_value_min=0.0,
            display_value_max=1.0,
            output_line=False,
            output_line_ends=((), ()),
            output_line_num_points=200,
            output_line_var=7,  # Mach number. 0~7: rho/u/v/et/uu/p/a/ma
            output_line_plot_var=0,
            display_gif_files=False):

        self.is_debug = False

        self.BlockSolver = BlockSolver
        self.Drawer = Drawer

        self.n_blocks = n_blocks
        self.block_dimensions = block_dimensions

        ## props
        self.ma0 = ma0
        self.gamma = 1.4
        self.p0 = 1.0 / self.gamma / self.ma0 / self.ma0
        self.e0 = self.p0 / (self.gamma - 1.0) + 0.5 * 1.0

        ## simulation
        self.is_dual_time = is_dual_time
        self.dt = dt
        self.t = 0.0

        ## convect flux
        self.convect_method = convect_method

        ## viscous Navier-Stokes simulation properties
        self.is_convect_calculated = True  # a switch to skip convect flux only for debug
        self.is_viscous = is_viscous
        if self.is_viscous:
            self.temp0_raw = temp0_raw
            self.re0 = re0  # re = rho * u * L / miu  = u * L / niu
            self.cs_sthland = 117.0 / self.temp0_raw
            self.pr_laminar = 0.72  # laminar prantl number
            self.cp0 = self.gamma / (self.gamma - 1.0) * self.p0

        ## realtime outputs
        ##  display simulation field
        self.gui_size = gui_size
        self.display_field = display_field
        self.display_value_min = display_value_min
        self.display_value_max = display_value_max
        ## switches, can be set later
        self.display_steps = 20
        self.display_show_grid = False
        self.display_show_xc = False
        self.display_show_velocity = False
        self.display_show_velocity_skip = (1, 1)
        self.display_show_surface = False
        self.display_show_surface_norm = False

        ##  plots one quantity along one line
        self.output_line = output_line
        self.output_line_ends = output_line_ends
        self.output_line_num_points = output_line_num_points
        self.output_line_var = output_line_var  # Mach number. 0~7: rho/u/v/et/uu/p/a/ma
        self.output_line_plot_var = output_line_plot_var  # output x on plot

        ## output gif
        self.display_gif_files = display_gif_files

        ## INIT blocks
        self.solvers = [
            (
                BlockSolver(
                    width,
                    height,
                    block_dimension[0],  # ni
                    block_dimension[1],  # nj
                    ma0,
                    dt,
                    is_dual_time=is_dual_time,
                    convect_method=convect_method,
                    is_viscous=is_viscous,
                    temp0_raw=temp0_raw,
                    re0=re0)
            )
            for block_dimension in block_dimensions
        ]

        ## connections are inter-blocked, govened by Multiblock Solver
        ## bc_connection_info stores boundaries that is interconnected
        ##      ((bc_def), (bc_other_side_def), number of cells)
        ##      with bc_def:
        ##              (start, march_plus_or_minus_direction(1/-1), 
        ##                 surface direction (0/1, i or j), surface start or end(0/1, surf i0/j0 or iend/jend))
        ##      sample: ((1, +1, 0, 0), (1, +1, 0, 1), nj)
        ##              means a boundary on i-surf-start side, from (1, 1) to (1, nj + 1), goes in j+ direction
        ##              connects to a boundary on i-surf-end side, from (ni, 1) to (ni, nj + 1), goes in j+ direction
        self.bc_connection_info = []

        ## INIT drawer
        self.drawer = Drawer(
                        width,
                        height,
                        n_blocks,
                        block_dimensions,
                        self.solvers,
                        gui_size=gui_size,
                        display_field=display_field,
                        display_value_min=display_value_min,
                        display_value_max=display_value_max,
                        output_line=output_line,
                        output_line_ends=output_line_ends,
                        output_line_num_points=output_line_num_points,
                        output_line_var=output_line_var,
                        output_line_plot_var=output_line_plot_var,
                        display_gif_files=display_gif_files)

        ## custom function injections for various custom simulations
        self.custom_init_func = None

    ########################
    # Call this before solve to set boundary connections
    # We do not use array clone here
    def set_bc_connection(self, connections):
        self.bc_connection_info = connections


    ########################
    # Set extra display
    def set_display_options(self, display_steps=20,
                            display_color_map=0,
                            display_show_grid=False,
                            display_show_xc=False,
                            display_show_velocity=False,
                            display_show_velocity_skip=(4, 4),
                            display_show_surface=False,
                            display_show_surface_norm=False,
                            output_monitor_points=[],
                            display_gif_files=False):
        self.display_steps = display_steps
        self.drawer.set_display_options(
            display_color_map=display_color_map,
            display_show_grid=display_show_grid,
            display_show_xc=display_show_xc,
            display_show_velocity=display_show_velocity,
            display_show_velocity_skip=display_show_velocity_skip,
            display_show_surface=display_show_surface,
            display_show_surface_norm=display_show_surface_norm,
            output_monitor_points=output_monitor_points,
            display_gif_files=display_gif_files)

    ###########
    # Set all solvers debug mode
    def set_debug(is_debug=True):
        self.is_debug = is_debug
        for solver in self.solvers:
            solver.is_debug = is_debug

    ########################
    # Set custom simulations
    def set_custom_simulations(self, custom_init_func):
        self.custom_init_func = custom_init_func
        for solver in self.solvers:
            solver.set_custom_simulations(custom_init_func)

    #--------------------------------------------------------------------------
    #  Inter-Block Connection Boundaries Conditions
    #
    #    Transfer gemoetric/field/surface data inter-blockly
    #--------------------------------------------------------------------------

    @ti.func
    def calc_bc_connection_positions(self, conn_info: ti.template(), ni, nj) -> ti.template():
        ## conn_info: (start index, march direction, surface direction, surface index (start/end))
        pos_start = ti.Vector([0, 0])
        direction_offset = ti.Vector([0, 0])   # bc marches in this direction from start elem
        bc_offset = ti.Vector([0, 0])          # virtual voxels indexes are pos + bc_offset for every bc cell

        index_start = conn_info[0]
        direction = conn_info[1]
        surf_ij = conn_info[2]
        surf_0n = conn_info[3]

        if (surf_ij == 0):     # i-surf
            direction_offset = ti.Vector([0, direction])
            if (surf_0n == 0): # i-0-surf
                pos_start = ti.Vector([1, index_start])
                bc_offset = ti.Vector([-1, 0])
            else:                   # i-n-surf
                pos_start = ti.Vector([ni, index_start])
                bc_offset = ti.Vector([1, 0])
        else:                       # j-surf
            direction_offset = ti.Vector([direction, 0])
            if (surf_0n == 0): # j-0-surf
                pos_start = ti.Vector([index_start, 1])
                bc_offset = ti.Vector([0, -1])
            else:                   # j-n-surf
                pos_start = ti.Vector([index_start, nj])
                bc_offset = ti.Vector([0, 1])

        return (pos_start, direction_offset, bc_offset)

    # offset to calc bc surf's index
    # NOTICE this is surf's plus direction, not always points to the bc side (positive/negative)
    # surf_between_normal = self.vec_surf[I + offset_surf_range, dir]
    @ti.func
    def calc_bc_surf_range(self, dir, end) -> ti.template():
        offset_surf_range = ti.Vector([0, 0])
        if dir == 0:  #x
            if end == 1:  #right
                offset_surf_range = ti.Vector([0, 0])
            else:
                offset_surf_range = ti.Vector([-1, 0])
        else:
            if end == 1:  #right
                offset_surf_range = ti.Vector([0, 0])
            else:
                offset_surf_range = ti.Vector([0, -1])
        return offset_surf_range

    @ti.kernel
    def bc_connection(self, solver: ti.template(), solver_other: ti.template(), bc_conn_info: ti.template(), bc_other_info: ti.template(), num: ti.template(), stage: ti.template()):
        # bc_conn_info, bc_other_info: (start index, march direction, surface direction, surface index (start/end)) with block index removed
        conn_pos_start, conn_direction_offset, conn_offset = self.calc_bc_connection_positions(bc_conn_info, solver.ni, solver.nj)
        other_pos_start, other_direction_offset, other_offset = self.calc_bc_connection_positions(bc_other_info, solver_other.ni, solver_other.nj)

        offset_surf_range = self.calc_bc_surf_range(bc_conn_info[2], bc_conn_info[3])
        conn_dir = bc_conn_info[2]
        other_offset_surf_range = self.calc_bc_surf_range(bc_other_info[2], bc_other_info[3])
        other_conn_dir = bc_other_info[2]

        for i in range(ti.static(num)):
            I = conn_pos_start + i * conn_direction_offset
            I_bc = I + conn_offset  # bc on this side
            I_other = other_pos_start + i * other_direction_offset          # real cell on other side

            I_surf = I + offset_surf_range
            I_surf_other = I_other + other_offset_surf_range

            if ti.static(stage == -1):
                solver.elem_area[I_bc] = solver_other.elem_area[I_other]
                ## elem width's 2 direction is i/j direction, not physical direction
                # solver.elem_width[I_bc] = solver_other.elem_width[I_other]
                if (bc_conn_info[2] == bc_other_info[2]):
                    solver.elem_width[I_bc] = solver_other.elem_width[I_other]
                else:
                    solver.elem_width[I_bc][0] = solver_other.elem_width[I_other][1]
                    solver.elem_width[I_bc][1] = solver_other.elem_width[I_other][0]
            elif ti.static(stage == 0):
                solver.q[I_bc] = solver_other.q[I_other]
            elif ti.static(stage == 1):
                # if ti.static(self.is_viscous):
                solver.gradient_v_c[I_bc] = solver_other.gradient_v_c[I_other]
                solver.gradient_temp_c[I_bc] = solver_other.gradient_temp_c[I_other]
            elif ti.static(stage == 10):
                solver.bc_connection_advect_flux_cell(I, I_bc, bc_conn_info[2], bc_conn_info[3]) # cell index, surf dir, surf end
            elif ti.static(stage == 20):
                solver.v_c[I_bc] = solver_other.v_c[I_other]
                solver.temp_c[I_bc] = solver_other.temp_c[I_other]
            elif ti.static(stage == 21):
                solver.v_surf[I_surf, conn_dir] = solver_other.v_surf[I_surf_other, other_conn_dir]
                solver.temp_surf[I_surf, conn_dir] = solver_other.temp_surf[I_surf_other, other_conn_dir]
            elif ti.static(stage == 22):
                solver.gradient_v_surf[I_surf, conn_dir] = solver_other.gradient_v_surf[I_surf_other, other_conn_dir]
                solver.gradient_temp_surf[I_surf, conn_dir] = solver_other.gradient_temp_surf[I_surf_other, other_conn_dir]
            # else: Exception (not in kernel), asset?

    ###############
    ## Transfer inter-block data here
    ##
    ## bc (set quantity on virtual voxels)
    ##
    ## stage: before and in loop, there're several points to set bc values
    ##   -1: geom patch (area, elem_width)
    ##    0: q on center
    ##    1: gradient uvt on center
    def bc_interblock(self, stage):
        # connection transfers are govened in MultiBlock class
        for (bc_conn, bc_other, num) in self.bc_connection_info:
            block = bc_conn[0]
            block_other = bc_other[0]
            # if (stage == 10):
                # print()
                # print(bc_conn, bc_other)
                # print()
            self.bc_connection(self.solvers[block], self.solvers[block_other], bc_conn[1:], bc_other[1:], num, stage)


    #--------------------------------------------------------------------------
    #  Time marching methods
    #
    #  Explicit
    #  Runge-Kutta 3rd
    #--------------------------------------------------------------------------
    def step(self):
        # RK-3
        for solver in self.solvers:
            solver.time_save_q()

        for i in range(3):
            # calc from new q
            for solver in self.solvers:
                solver.bc(0)
            self.bc_interblock(0)

            for solver in self.solvers:
                solver.clear_flux()
            
            if self.is_viscous:
                for solver in self.solvers:
                    # self.flux_diffusion()
                    solver.calc_u_temp_center()
                    # solver.bc(20)
                self.bc_interblock(20)

                for solver in self.solvers:
                    solver.flux_diffusion_interp_qsurf()
                    solver.bc(21) # set q on surf
                self.bc_interblock(21)

                for solver in self.solvers:
                    solver.flux_diffusion_integrate_gradient_center()
                    solver.bc(1) # set gradient on virtual center
                self.bc_interblock(1)

                for solver in self.solvers:
                    solver.flux_diffusion_calc_gradient_surf()
                    solver.bc(22) # set gradient on surf
                self.bc_interblock(22)

                for solver in self.solvers:
                    solver.calc_flux_diffusion()
                    # TODO: be connections bc 1/20/21/22 in multiblock

            for solver in self.solvers:
                solver.flux_advect()
                solver.bc(10)   # advect flux on bc
                ## solver.bc_fake(10)
            self.bc_interblock(10)

            for solver in self.solvers:
                solver.time_march_rk3(i)


    def step_dual(self, step_index):
        ### RK-3
        for solver in self.solvers:
            solver.time_save_q_dual()

        ## dual time, inner time step
        for _ in range(3):
            for solver in self.solvers:
                solver.time_save_q_dual_sub()

            ## RK-3
            for i in range(3):
                # calc from new q
                for solver in self.solvers:
                    solver.bc(0)
                self.bc_interblock(0)

                for solver in self.solvers:
                    solver.clear_flux()

                if self.is_viscous:
                    for solver in self.solvers:
                        # self.flux_diffusion()
                        solver.calc_u_temp_center()
                        # solver.bc(20)
                    self.bc_interblock(20)

                    for solver in self.solvers:
                        solver.flux_diffusion_interp_qsurf()
                        solver.bc(21) # set q on surf
                    self.bc_interblock(21)

                    for solver in self.solvers:
                        solver.flux_diffusion_integrate_gradient_center()
                        solver.bc(1) # set gradient on virtual center
                    self.bc_interblock(1)

                    for solver in self.solvers:
                        solver.flux_diffusion_calc_gradient_surf()
                        solver.bc(22) # set gradient on surf
                    self.bc_interblock(22)

                    for solver in self.solvers:
                        solver.calc_flux_diffusion()

                for solver in self.solvers:
                    solver.flux_advect()
                    solver.bc(10)   # advect flux on bc
                self.bc_interblock(10)

                for solver in self.solvers:
                    solver.time_march_rk3_dual(i, step_index)

        # ## update main
        # for solver in self.solvers:
        #     solver.time_save_q_dual_sub()
        # # calc from new q
        # for solver in self.solvers:
        #     solver.bc(0)
        # self.bc_interblock(0)

        # for solver in self.solvers:
        #     solver.clear_flux()

        # if self.is_viscous:
        #     for solver in self.solvers:
        #         # self.flux_diffusion()
        #         solver.calc_u_temp_center()
        #         # solver.bc(20)
        #     self.bc_interblock(20)

        #     for solver in self.solvers:
        #         solver.flux_diffusion_interp_qsurf()
        #         solver.bc(21) # set q on surf
        #     self.bc_interblock(21)

        #     for solver in self.solvers:
        #         solver.flux_diffusion_integrate_gradient_center()
        #         solver.bc(1) # set gradient on virtual center
        #     self.bc_interblock(1)

        #     for solver in self.solvers:
        #         solver.flux_diffusion_calc_gradient_surf()
        #         solver.bc(22) # set gradient on surf
        #     self.bc_interblock(22)

        #     for solver in self.solvers:
        #         solver.calc_flux_diffusion()

        # for solver in self.solvers:
        #     solver.flux_advect()
        #     solver.bc(10)   # advect flux on bc
        # self.bc_interblock(10)

        # for solver in self.solvers:
        #     solver.time_march_rk3_dual_last()        


    #--------------------------------------------------------------------------
    #  Main loop
    #--------------------------------------------------------------------------

    def run(self):
        ### TODO: move GUI into Drawer class
        self.gui = ti.GUI("2D FVM Supersonic",
                          res=self.gui_size,
                          background_color=0x4f9297)

        self.drawer.set_gui(self.gui)

        for block in range(self.n_blocks):
            self.solvers[block].init()

        self.bc_interblock(-1)

        self.drawer.init_display()

        pause = False
        # step_index = 1
        # # start from van leer
        # for solver in self.solvers:
        #     solver.convect_method = 0

        step_index = 0
        while self.gui.running:
            for e in self.gui.get_events(ti.GUI.PRESS):
                if e.key in [ti.GUI.ESCAPE, ti.GUI.EXIT]:
                    self.gui.running = False
                elif e.key in [ti.GUI.SPACE]:
                    pause = not pause

            if pause:
                ## TODO: this will cause problems?
                # # time.sleep(1)
                if self.display_field:
                    self.drawer.display(step_index)
                continue

            ## simulation step
            for step in range(self.display_steps):
                if self.is_dual_time:
                    self.step_dual(step_index)
                else:
                    self.step()
                # for block in range(self.n_blocks):
                #     self.solvers[block].step()
                self.t += self.dt
                for block in range(self.n_blocks):
                    self.solvers[block].t = self.t

            ## TODO: more useful information to console
            print()
            print(f't: {self.t:.03f}')
            if self.display_field:
                self.drawer.display(step_index)
            if self.output_line:
                self.drawer.display_output_line()

            step_index += 1
            # if step_index == 100:
            #     for solver in self.solvers:
            #         solver.convect_method = self.convect_method
