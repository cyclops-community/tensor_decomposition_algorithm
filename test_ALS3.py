import numpy as np
import sys
import time
import CPD.common_kernels as ck
import CPD.lowr_ALS3 as lowr_ALS
import CPD.standard_ALS3 as stnd_ALS
import CPD.sliced_ALS3 as slic_ALS
import tensors.synthetic_tensors as stsrs
import argparse
import arg_defs as arg_defs
import csv
import os
from os.path import dirname, join
from pathlib import Path

parent_dir = dirname(__file__)
results_dir = join(parent_dir, 'results')

def test_rand_naive(tenpy,s,R,num_iter,sp_frac,sp_res,mm_test=False,pois_test=False,csv_writer=None,Regu=None):
    if mm_test == True:
        [A,B,C,T,O] = stsrs.init_mm(tenpy,s,R)
    elif pois_test == True:
        [A,B,C,T,O] = stsrs.init_poisson(tenpy,s,R)
    else:
        [A,B,C,T,O] = stsrs.init_rand3(tenpy,s,R,sp_frac)
    time_all = 0.
    for i in range(num_iter):
        if sp_res:
            res = ck.get_residual_sp3(tenpy,O,T,A,B,C)
        else:
            res = ck.get_residual3(tenpy,T,A,B,C)
        if tenpy.is_master_proc():
            print("Residual is", res)
            # write to csv file
            csv_writer.writerow([
                i, time_all, res
            ])
        t0 = time.time()
        [A,B,C] = stnd_ALS.dt_ALS_step(tenpy,T,A,B,C,Regu)
        t1 = time.time()
        tenpy.printf("Sweep took", t1-t0,"seconds")
        time_all += t1-t0
    tenpy.printf("Naive method took",time_all,"seconds overall")

def test_rand_sliced(tenpy,s,R,num_iter,sp_frac,sp_res,num_slices,mm_test=False,pois_test=False,csv_writer=None,Regu=None):
    if mm_test == True:
        [A,B,C,T,O] = stsrs.init_mm(tenpy,s,R)
    elif pois_test == True:
        [A,B,C,T,O] = stsrs.init_poisson(tenpy,s,R)
    else:
        [A,B,C,T,O] = stsrs.init_rand3(tenpy,s,R,sp_frac)
    time_all = 0.
    Ta = []
    Tb = []
    Tc = []

    b = int((s+num_slices-1)/num_slices)
    for i in range(num_slices):
        st = i*b
        end = min(st+b,s)
        Ta.append(T[st:end,:,:])
        Tb.append(T[:,st:end,:])
        Tc.append(T[:,:,st:end])
        
    for i in range(num_iter):
        if sp_res:
            res = ck.get_residual_sp3(tenpy,O,T,A,B,C)
        else:
            res = ck.get_residual3(tenpy,T,A,B,C)
        if tenpy.is_master_proc():
            print("Residual is", res)
            # write to csv file
            csv_writer.writerow([
                i, time_all, res
            ])
        t0 = time.time()
        [A,B,C] = slic_ALS.sliced_ALS_step(tenpy,Ta,Tb,Tc,A,B,C,Regu)
        t1 = time.time()
        tenpy.printf("Sweep took", t1-t0,"seconds")
        time_all += t1-t0
    tenpy.printf("Naive method took",time_all,"seconds overall")


def test_rand_lowr(tenpy,s,R,r,num_iter,num_lowr_init_iter,sp_frac,sp_ul=False,sp_res=False,mm_test=False,pois_test=False,csv_writer=None,Regu=None,sp_update_factor=False):
    if mm_test == True:
        [A,B,C,T,O] = stsrs.init_mm(tenpy,s,R)
    elif pois_test == True:
        [A,B,C,T,O] = stsrs.init_poisson(tenpy,s,R)
    else:
        [A,B,C,T,O] = stsrs.init_rand3(tenpy,s,R,sp_frac)
    time_init = 0.

    for i in range(num_lowr_init_iter):
        if sp_res:
            res = ck.get_residual_sp3(tenpy,O,T,A,B,C)
        else:
            res = ck.get_residual3(tenpy,T,A,B,C)
        if tenpy.is_master_proc():
            print("Residual is", res)
            # write to csv file
            csv_writer.writerow([
                i, time_init, res
            ])
        t0 = time.time()
        [A,B,C] = stnd_ALS.dt_ALS_step(tenpy,T,A,B,C,Regu)
        t1 = time.time()
        tenpy.printf("Full-rank sweep took", t1-t0,"seconds, iteration ",i)
        time_init += t1-t0
        tenpy.printf("Total time is ", time_init)
    time_lowr = time.time()

    if num_lowr_init_iter == 0:
        tenpy.printf("Initializing leaves from low rank factor matrices")
        A1 = tenpy.random((s,r))
        B1 = tenpy.random((s,r))
        C1 = tenpy.random((s,r))
        A2 = tenpy.random((r,R))
        B2 = tenpy.random((r,R))
        C2 = tenpy.random((r,R))
        [RHS_A,RHS_B,RHS_C] = lowr_ALS.build_leaves_lowr(tenpy,T,A1,A2,B1,B2,C1,C2)
        A = tenpy.dot(A1,A2)
        B = tenpy.dot(B1,B2)
        C = tenpy.dot(C1,C2)
        tenpy.printf("Done initializing leaves from low rank factor matrices")
    else:
        [RHS_A,RHS_B,RHS_C] = lowr_ALS.build_leaves(tenpy,T,A,B,C)

    time_lowr = time.time() - time_lowr
    for i in range(num_iter-num_lowr_init_iter):
        if sp_res:
            res = ck.get_residual_sp3(tenpy,O,T,A,B,C)
        else:
            res = ck.get_residual3(tenpy,T,A,B,C)
        if tenpy.is_master_proc():
            print("Residual is", res)
            # write to csv file
            csv_writer.writerow([
                i+num_lowr_init_iter, time_init+time_lowr, res
            ])
        t0 = time.time()
        symb_uls = "update_leaves"
        if sp_ul == True:
              symb_uls = "update_leaves_sp"
        symb_uf = "solve_sys_lowr"
        if sp_update_factor == True:
              symb_uf = "solve_sys_lowr_sp"
        [A,B,C,RHS_A,RHS_B,RHS_C] = lowr_ALS.lowr_msdt_step(tenpy,T,A,B,C,RHS_A,RHS_B,RHS_C,r,Regu,symb_uls,symb_uf)
        t1 = time.time()
        tenpy.printf("Low-rank sweep took", t1-t0,"seconds, Iteration",i)
        time_lowr += t1-t0
        tenpy.printf("Total time is ", time_lowr)
    tenpy.printf("Low rank method (sparse update leaves =",sp_ul,") took",time_init,"for initial full rank steps",time_lowr,"for low rank steps and",time_init+time_lowr,"seconds overall")


def test_rand_lowr_dt(tenpy,s,R,r,num_iter,num_lowr_init_iter,sp_frac,sp_ul=False,sp_res=False,mm_test=False,pois_test=False,csv_writer=None,Regu=None,sp_update_factor=False,num_inter_iter=10):
    if mm_test == True:
        [A,B,C,T,O] = stsrs.init_mm(tenpy,s,R)
    elif pois_test == True:
        [A,B,C,T,O] = stsrs.init_poisson(tenpy,s,R)
    else:
        [A,B,C,T,O] = stsrs.init_rand3(tenpy,s,R,sp_frac)
    time_init = 0.

    for i in range(num_lowr_init_iter):
        if sp_res:
            res = ck.get_residual_sp3(tenpy,O,T,A,B,C)
        else:
            res = ck.get_residual3(tenpy,T,A,B,C)
        if tenpy.is_master_proc():
            print("Residual is", res)
            # write to csv file
            csv_writer.writerow([
                i, time_init, res
            ])
        t0 = time.time()
        [A,B,C] = stnd_ALS.dt_ALS_step(tenpy,T,A,B,C,Regu)
        t1 = time.time()
        tenpy.printf("Full-rank sweep took", t1-t0,"seconds, iteration ",i)
        time_init += t1-t0
        tenpy.printf("Total time is ", time_init)
    time_lowr = time.time()

    if num_lowr_init_iter == 0:
        tenpy.printf("Initializing leaves from low rank factor matrices")
        A1 = tenpy.random((s,r))
        B1 = tenpy.random((s,r))
        C1 = tenpy.random((s,r))
        A2 = tenpy.random((r,R))
        B2 = tenpy.random((r,R))
        C2 = tenpy.random((r,R))
        [RHS_A,RHS_B,RHS_C] = lowr_ALS.build_leaves_lowr(tenpy,T,A1,A2,B1,B2,C1,C2)
        A = tenpy.dot(A1,A2)
        B = tenpy.dot(B1,B2)
        C = tenpy.dot(C1,C2)
        tenpy.printf("Done initializing leaves from low rank factor matrices")
    else:
        [RHS_A,RHS_B,RHS_C] = lowr_ALS.build_leaves(tenpy,T,A,B,C)

    time_lowr = time.time() - time_lowr
    factor_matrices = ["A","B","C"]
    factor_matrix_index = 0
    counter = 0
    for i in range(num_iter-num_lowr_init_iter):
        if sp_res:
            res = ck.get_residual_sp3(tenpy,O,T,A,B,C)
        else:
            res = ck.get_residual3(tenpy,T,A,B,C)
        if tenpy.is_master_proc():
            print("Residual is", res)
            # write to csv file
            csv_writer.writerow([
                i+num_lowr_init_iter, time_init+time_lowr, res
            ])
        t0 = time.time()
        symb_uls = "update_leaves"
        if sp_ul == True:
              symb_uls = "update_leaves_sp"
        symb_uf = "solve_sys_lowr"
        if sp_update_factor == True:
              symb_uf = "solve_sys_lowr_sp"
        if counter == num_inter_iter:
            counter = 0
            factor_matrix_index = (factor_matrix_index + 1)%3
        [A,B,C,RHS_A,RHS_B,RHS_C] = lowr_ALS.lowr_dt_step(tenpy,T,A,B,C,RHS_A,RHS_B,RHS_C,r,Regu,symb_uls,symb_uf,factor_matrices[factor_matrix_index])
        counter += 1
        t1 = time.time()
        tenpy.printf("Low-rank sweep took", t1-t0,"seconds, Iteration",i)
        time_lowr += t1-t0
        tenpy.printf("Total time is ", time_lowr)
    tenpy.printf("Low rank method (sparse update leaves =",sp_ul,") took",time_init,"for initial full rank steps",time_lowr,"for low rank steps and",time_init+time_lowr,"seconds overall")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    arg_defs.add_general_arguments(parser)
    args, _ = parser.parse_known_args()

    # Set up CSV logging
    csv_path = join(results_dir, arg_defs.get_file_prefix(args)+'.csv')
    is_new_log = not Path(csv_path).exists()
    csv_file = open(csv_path, 'a')#, newline='')
    csv_writer = csv.writer(
        csv_file, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)

    s = args.s
    R = args.R
    r = args.r
    num_iter = args.num_iter
    num_lowr_init_iter = args.num_lowr_init_iter
    sp_frac = args.sp_fraction
    sp_ul = args.sp_updatelowrank
    sp_res = args.sp_res
    run_naive = args.run_naive
    run_lowr = args.run_lowrank
    run_lowr_dt = args.run_lowrank_dt
    num_inter_iter = args.num_inter_iter
    mm_test = args.mm_test
    num_slices = args.num_slices
    pois_test = args.pois_test
    sp_update_factor = args.sp_update_factor
    tlib = args.tlib

    if tlib == "numpy":
        import backend.numpy_ext as tenpy
    elif tlib == "ctf":
        import backend.ctf_ext as tenpy
    else:
        print("ERROR: Invalid --tlib input")

    if tenpy.is_master_proc():
        # print the arguments
        for arg in vars(args) :
            print( arg+':', getattr(args, arg))
        # initialize the csv file
        if is_new_log:
            csv_writer.writerow([
                'iterations', 'time', 'residual'
            ])

    tenpy.seed(1)

    Regu = args.regularization * tenpy.eye(R,R)

    if run_naive:
        if num_slices == 1:
            tenpy.printf("Testing naive version, printing residual before every ALS sweep")
            test_rand_naive(tenpy,s,R,num_iter,sp_frac,sp_res,mm_test,pois_test,csv_writer,Regu)
        else:
            tenpy.printf("Testing sliced version, printing residual before every ALS sweep")
            test_rand_sliced(tenpy,s,R,num_iter,sp_frac,sp_res,num_slices,mm_test,pois_test,csv_writer,Regu)
    if run_lowr:
        tenpy.printf("Testing low rank msdt version, printing residual before every ALS sweep")
        test_rand_lowr(tenpy,s,R,r,num_iter,num_lowr_init_iter,sp_frac,sp_ul,sp_res,mm_test,pois_test,csv_writer,Regu,sp_update_factor)
    if run_lowr_dt:
        tenpy.printf("Testing low rank dt version, printing residual before every ALS sweep")
        test_rand_lowr_dt(tenpy,s,R,r,num_iter,num_lowr_init_iter,sp_frac,sp_ul,sp_res,mm_test,pois_test,csv_writer,Regu,sp_update_factor,num_inter_iter)
