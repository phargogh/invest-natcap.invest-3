from libc.math cimport atan2
from libc.math cimport sin
import math
cimport numpy as np
import numpy as np

import cython

cdef extern from "stdlib.h":
    void* malloc(size_t size)
    void free(void* ptr)

cdef extern from "math.h":
    double atan2(double x, double x)

#cdef extern from "math.h":
#    int abs(int x)


cdef inline int int_round(float x): return <int>(x) if x-<int>x <= 0.5  else <int>(x+1)

class NotAtSea(Exception): pass
@cython.boundscheck(False)
def list_extreme_cell_angles_cython(array_shape, viewpoint_coords):
    """List the minimum and maximum angles spanned by each cell of a
        rectangular raster if scanned by a sweep line centered on
        viewpoint_coords.
    
        Inputs:
            -array_shape: a shape tuple (rows, cols) as is created from
                calling numpy.ndarray.shape()
            -viewpoint_coords: a 2-tuple of coordinates similar to array_shape
            where the sweep line originates
            
        returns a tuple (min, center, max, I, J) with min, center and max 
        Nx1 numpy arrays of each raster cell's minimum, center, and maximum 
        angles and coords as two Nx1 numpy arrays of row and column of the 
        coordinate of each point.
    """
    viewpoint = np.array(viewpoint_coords)

    pi = 3.1415926535897932384626433852
    two_pi = 2. * pi
    rad_to_deg = 180.0 / pi
    deg_to_rad = 1.0 / rad_to_deg

    cdef:
        int min_angle_id = 0
        int max_angle_id = 1
        int viewpoint_row = viewpoint_coords[0]
        int viewpoint_col = viewpoint_coords[1]
        int cell_row = 0
        int cell_col = 0
        int viewpoint_to_cell_row = 0
        int viewpoint_to_cell_col = 0
        int array_rows = array_shape[0]
        int array_cols = array_shape[1]
        int cell_count = array_rows * array_cols
        double min_corner_row = 0
        double min_corner_col = 0
        double max_corner_row = 0
        double max_corner_col = 0
        double min_corner_offset_row = 0
        double min_corner_offset_col = 0
        double max_corner_offset_row = 0
        double max_corner_offset_col = 0

    cdef size_t SECTOR_SIZE = 4
    cdef size_t POINT_SIZE = 2
    cdef size_t min_point_id
    cdef size_t max_point_id
    cdef double *extreme_cell_points = [ \
    0.5, -0.5, -0.5, -0.5, \
    0.5, 0.5, -0.5, -0.5, \
    0.5, 0.5, 0.5, -0.5, \
    -0.5, 0.5, 0.5, -0.5, \
    -0.5, 0.5, 0.5, 0.5, \
    -0.5, -0.5, 0.5, 0.5, \
    -0.5, -0.5, -0.5, 0.5, \
    0.5, -0.5, -0.5, 0.5]

    print('listing extreme cell angles')

    cdef np.ndarray I = np.ndarray(cell_count -1, dtype = np.int32)
    cdef np.ndarray J = np.ndarray(cell_count -1, dtype = np.int32)

    cdef double *min_a_ptr = <double *>malloc((cell_count-1) * sizeof(double))
    cdef double *a_ptr = <double *>malloc((cell_count-1) * sizeof(double))
    cdef double *max_a_ptr = <double *>malloc((cell_count-1) * sizeof(double))

    # Loop through the rows
    cdef:
        int cell_id = 0
        int row = 0
        int col = 0
        int sector = 0

    for row in range(array_rows):
        if (cell_count > 1000) and \
            (cell_id % (cell_count/1000)) == 0:
            progress = round(float(cell_id) / cell_count * 100.,1)
            print(str(progress) + '%')

        viewpoint_to_cell_row = row - viewpoint_row
        # Loop through the columns    
        for col in range(array_cols):
            viewpoint_to_cell_col = col - viewpoint_col
            # Show progress in 0.1% increment
            # Skip if cell falls on the viewpoint
            if (row == viewpoint_row) and (col == viewpoint_col):
                continue
            # cell coordinates
            # Update list of rows and list of cols
            #I.append(row)
            I[cell_id] = row
            #J.append(col)
            J[cell_id] = col
            # Compute the angle of the cell center
            angle = atan2(-(row - viewpoint_row), col - viewpoint_col)
            a_ptr[cell_id] = (angle + two_pi) % two_pi
            # find index in extreme_cell_points that corresponds to the current
            # angle to compute the offset from cell center
            # This line only discriminates between 4 axis-aligned angles
            sector = int(4. * a_ptr[cell_id] / two_pi) * 2
            # The if statement adjusts for all the 8 angles
            if abs(viewpoint_to_cell_row * viewpoint_to_cell_col) > 0:
                sector += 1
            # adjust wrt 8 angles
            min_point_id = sector * SECTOR_SIZE
            min_corner_offset_row = extreme_cell_points[min_point_id]
            min_corner_offset_col = extreme_cell_points[min_point_id + 1]
            max_point_id = min_point_id + POINT_SIZE
            max_corner_offset_row = extreme_cell_points[max_point_id]
            max_corner_offset_col = extreme_cell_points[max_point_id + 1]
            # Use the offset to compute extreme angles
            min_corner_row = viewpoint_to_cell_row + min_corner_offset_row
            min_corner_col = viewpoint_to_cell_col + min_corner_offset_col
            min_angle = atan2(-min_corner_row, min_corner_col)
            min_a_ptr[cell_id] = (min_angle + two_pi) % two_pi 
            
            max_corner_row = viewpoint_to_cell_row + max_corner_offset_row
            max_corner_col = viewpoint_to_cell_col + max_corner_offset_col
            max_angle = atan2(-max_corner_row, max_corner_col)
            max_a_ptr[cell_id] = (max_angle + two_pi) % two_pi
            cell_id += 1
    # Copy C-array contents to numpy arrays:
    # TODO: use memcpy if possible (or memoryviews?)
    # Copy C arrays to numpy arrays
    min_angles = np.ndarray(cell_count -1, dtype = np.float)
    angles = np.ndarray(cell_count -1, dtype = np.float)
    max_angles = np.ndarray(cell_count -1, dtype = np.float)
    for i in range(cell_count-1):
        min_angles[i] = min_a_ptr[i]
        angles[i] = a_ptr[i]
        max_angles[i] = max_a_ptr[i]
    free(min_a_ptr)
    free(a_ptr)
    free(max_a_ptr)
    # Copy a_ptr to angles    
    print('done')
    return (min_angles, angles, max_angles, I, J)


