"""
Some elements of the finite difference routines were adapted from HP Langtangen's wonderful book on the FD method for python:

https://hplgit.github.io/fdm-book/doc/pub/book/html/._fdm-book-solarized001.html
"""

import numpy as np
from scipy.integrate import simps

class Wave1D:
    """
    A utility class for simulating the wave equation in 1 dimension using a finite difference
    """
    def __init__(self,config):
        """
        Constructor 1 dimensional wave system

        Inputs:
            config:  A dict containing parameters for the system, which must have the following keys:

            time_interval:  (float > 0) the temporal interval between time steps
            wave_speed: (float > 0) the speed of standing waves on the bridge, related to material tension
            system_length: (float > 0) the lengthe of the system
            num_lattice_points: (int > 0) how many discrete points along the length of the system to use for
                the finite difference scheme
            num_force_points: (int > 0) how many pistons the system has
            force_width: (int > 0) how wide the gaussian spread of each piston is

        """

        self.dt = config['time_interval']
        self.c_speed = config['wave_speed']
        self.L = config['system_length']
        self.Nx = config['num_lattice_points']
        # How many points along the domain can impulse force be applied
        self.num_force_points = config['num_force_points']
        # Set the locations of the force application
        self.force_locations = np.linspace(0.0,self.L,self.num_force_points+2)[1:self.num_force_points+1]
        # How wide is the profile of each impulse force, must be > 0
        self.force_width = config['force_width']
        # Scale the force width by system length
        self.force_width *= self.L

        # The lattice spacing
        self.dx = float(self.L)/float(self.Nx)

        # Mesh points in space
        self.x_mesh = np.linspace(0.0,self.L,self.Nx+1)

        # The courant number
        self.C = self.c_speed *self.dt/self.dx
        self.C2 = self.C**2 #helper number

        # Recalibrate the resolutions to account for rounding
        self.dx = self.x_mesh[1] - self.x_mesh[0]

        # We set up the conditions of the system before warmup period

        # The system is always initially at rest
        self.Velocity_0 = lambda x: 0

        # We assume the system starts completely flat
        self.Initial_Height = lambda x: 0


        # Allocate memory for the recursive solution arrays
        self.height     = np.zeros(self.Nx + 1)   # Solution array at new time level
        self.height_n   = np.zeros(self.Nx + 1)   # Solution at 1 time level back
        self.height_nm1 = np.zeros(self.Nx + 1)   # Solution at 2 time levels back


        self.height_traj=[]
        self.action_traj=[]
        self.reset()

    def reset(self):
        """
        Resets the state of the wave system
        """
        # We reset the time and step index
        self.t = 0
        self.n = 0

        # We set the force vals to zero
        self.force_vals = np.zeros(self.num_force_points)


        # We set the initial condition of the solution 1 time level back
        for i in range(0,self.Nx+1):
            self.height_n[i]=self.Initial_Height(self.x_mesh[i])

        # We do a special first step for the finite difference scheme
        for i in range(1,self.Nx):
            self.height[i] =self.height_n[i] + self.dt*self.Velocity_0(self.x_mesh[i])
            self.height[i]+=0.5*self.C2*(self.height_n[i-1] - 2*self.height_n[i] + self.height_n[i+1])
            self.height[i]+=0.5*(self.dt**2)*self.impulse_term(self.x_mesh[i])
        # Force boundary conditions
        self.height[0]=0
        self.height[self.Nx]=0
        # Switch solution steps
        self.height_nm1[:] = self.height_n
        self.height_n[:] = self.height

    def single_step(self):
        """
        Run a single step of the wave equation finite difference dynamics
        """

        self.t += self.dt
        self.n += 1
        for i in range(1,self.Nx):
            self.height[i] = -self.height_nm1[i] + 2*self.height_n[i]
            self.height[i] += self.C2*(self.height_n[i-1] - 2*self.height_n[i] + self.height_n[i+1])
            self.height[i] += (self.dt**2)*self.impulse_term(self.x_mesh[i])
        # Force boundary conditions
        self.height[0] = 0
        self.height[self.Nx] = 0

        # Switch solution steps
        self.height_nm1[:] = self.height_n
        self.height_n[:] = self.height

    def take_in_action(self,action):
        """
        This method acts as the interface where the agent applies an action to environment.
        For this simulator, it's simply a setter method for the force_vals attribute that
        determine the profile of the impulse term.
        """
        self.force_vals = np.copy(action)

    def impulse_term(self,x):
        """
        The function definition for the active damping terms

        Inputs:
            x - a scalar, position in the domain
            force_vals - A vector of shape (self.num_force_points),
                the (signed) values of the force at each piston point
        """
        return np.sum(self.force_vals*np.exp(-0.5* ((x-self.force_locations)**2 )/self.force_width))

    def get_impulse_profile(self):
        """
        A utility function for returning an array representing the shape of the resulting impulse
        force, this is used for rendering the history of actions taken by the agent.

        Inputs:
            force_vals - A vector of shape (self.num_force_points),
                the (signed) values of the force at each piston point
        """
        profile = []
        for i in range(self.Nx+1):
            profile.append(self.impulse_term(self.x_mesh[i]))
        return np.array(profile)

    def get_observation(self):
        """
        This is an interface that returns the observation of the system, which is modeled
        as the state of the wave system for the current timestep, previous timestep, and
        twice previous timestep.

        Outputs:
            observation - An array of shape (1,self.Nx+1,3).  observation[0,:,0]= self.height,
                observation[0,:,1]=self.height_n, and observation[0,:,2]=self.height_nm1
        """

        observation = np.zeros((1,self.Nx+1,3))
        observation[0,:,0]= self.height
        observation[0,:,1]=self.height_n
        observation[0,:,2]=self.height_nm1
        return observation

    def energy(self):
        """
        Computes the internal energy of the system based upon the integral functional for
        the 1-D wave equation.  Additionally we add an L2 norm regularizer

        See http://web.math.ucsb.edu/~grigoryan/124A/lecs/lec7.pdf for details
        """

        dudt = (self.height-self.height_nm1)/self.dt # Time derivative
        dudx = np.gradient(self.height,self.x_mesh) # Space derivative

        space_term = -self.height*np.gradient(dudx,self.x_mesh) # Alternative tension energy
        energy_density = dudt**2 + (self.C**2)*(dudx**2)
        energy_density += self.height**2 # Regularize with L2 norm
        # Energy_density = dudt**2 + (self.c_speed**2)*space_term
        return 0.5*simps(energy_density,self.x_mesh)
