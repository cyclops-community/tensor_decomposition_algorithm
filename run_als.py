import numpy as np
import sys
import time
import os
import argparse
import csv
from pathlib import Path
from os.path import dirname, join
import tensors.synthetic_tensors as synthetic_tensors
import tensors.real_tensors as real_tensors
import argparse
import arg_defs as arg_defs
import csv

from utils import save_decomposition_results

parent_dir = dirname(__file__)
results_dir = join(parent_dir, 'results')

def CP_ALS(tenpy,A,input_tensor,O,num_iter,sp_res,csv_file=None,Regu=None,method='DT',hosvd=0,args=None,res_calc_freq=1,nls_tol= 1e-05,cg_tol = 1e-12, grad_tol = 1e-05,num=1,switch_tol=0.1,own_cg=False,nls_iter = 2, als_iter = 30, maxiter =0):

    from CPD.common_kernels import get_residual_sp, get_residual
    from CPD.standard_ALS import CP_DTALS_Optimizer, CP_PPALS_Optimizer, CP_partialPPALS_Optimizer
    from CPD.lowr_ALS import CP_DTLRALS_Optimizer
    from CPD.NLS import CP_fastNLS_Optimizer, CP_ALSNLS_Optimizer,CP_safeNLS_Optimizer

    
    if csv_file is not None:
        csv_writer = csv.writer(
            csv_file, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)

    T, transformer = None, None
    if args is not None:
        if args.hosvd != 0:
            from Tucker.common_kernels import hosvd
            transformer, T = hosvd(tenpy, input_tensor, args.hosvd_core_dim, compute_core=True)
        else:
            T = input_tensor
    else:
        T = input_tensor

    if Regu is None:
        Regu = 0
        
    decrease= True
    increase=False
    
    flag = False
    iters = 0

    normT = tenpy.vecnorm(T)
    
    if maxiter == 0:
        maxiter = len(A)*(A[0].shape[0])*(A[0].shape[1])
        

    time_all = 0.
    if args is None:
        optimizer = CP_DTALS_Optimizer(tenpy,T,A)
    else:
        optimizer_list = {
            'DT': CP_DTALS_Optimizer(tenpy,T,A),
            'DTLR': CP_DTLRALS_Optimizer(tenpy,T,A,args),
            'PP': CP_PPALS_Optimizer(tenpy,T,A,args),
            'partialPP': CP_partialPPALS_Optimizer(tenpy,T,A,args),
            'NLS': CP_fastNLS_Optimizer(tenpy,T,A,maxiter,cg_tol,num,args),
            'NLSALS': CP_ALSNLS_Optimizer(tenpy,T,A,cg_tol,num,switch_tol),
            'SNLS': CP_safeNLS_Optimizer(tenpy,T,A, maxiter,cg_tol,num,als_iter,nls_iter)
        }
        optimizer = optimizer_list[method]

    fitness_old = 0
    for i in range(num_iter):

        if i % res_calc_freq == 0 or i==num_iter-1:
            if sp_res:
                res = get_residual_sp(tenpy,O,T,A)
            else:
                res = get_residual(tenpy,T,A)
            fitness = 1-res/normT

            if tenpy.is_master_proc():
                print("[",i,"] Residual is", res, "fitness is: ", fitness)
                # write to csv file
                if csv_file is not None:
                    if method == 'NLS':
                        csv_writer.writerow([iters, time_all, res, fitness])
                    else:
                        csv_writer.writerow([i, time_all, res, fitness])
                    csv_file.flush()
        '''if i != 0 and method == 'NLS':
            if tenpy.vecnorm(optimizer.gradient()) < grad_tol:
                print('Gradient norm less than tolerance in',i,'iterations')
                break'''
            
        if res<nls_tol:
            print('Method converged in',i,'iterations')
            break
        t0 = time.time()
        # Regu = 1/(i+1)
        print("Regu is:",Regu)
        if own_cg and method == 'NLS' :
            [A,iters] = optimizer.step2(Regu)
        elif method == 'NLS':
            [A,iters] = optimizer.step(Regu)
            
        elif method == 'SNLS':
            A = optimizer.step(Regu,res,fitness)
        else:
            A = optimizer.step(Regu)
            
        t1 = time.time()
        tenpy.printf("[",i,"] Sweep took", t1-t0,"seconds")
        
        time_all += t1-t0
        
            
        
        fitness_old = fitness
        
        
        if method == "NLS" :
            if res < 1:
                flag = True
            
            
                
            else:
                if Regu < 1e-05:
                    increase=True
                    decrease=False
                
                if Regu > 1e-01:
                    decrease= True
                    increase=False
                        
                
                
            if increase:
                Regu = Regu*2
                
            elif decrease:
                Regu = Regu/2
        
            #if Regu < 1e-03:
            #    print("CHANGED REGU")
            #    Regu= orig_Regu
        
            
        

    if hosvd != 0:
        A_fullsize = []
        norm_input = tenpy.vecnorm(input_tensor)
        for i in range(T.ndim):
            A_fullsize.append(tenpy.dot(transformer[i],A[i]))
        if sp_res:
            res = get_residual_sp(tenpy,O,input_tensor,A_fullsize)
        else:
            res = get_residual(tenpy,input_tensor,A_fullsize)
        fitness = 1-res/norm_input
        tenpy.printf(method, "with hosvd, residual is", res, "fitness is: ", fitness)

    tenpy.printf(method+" method took",time_all,"seconds overall")

    if args.save_tensor:
        folderpath = join(results_dir, arg_defs.get_file_prefix(args))
        save_decomposition_results(T,A,tenpy,folderpath)

    return res

def Tucker_ALS(tenpy,A,T,O,num_iter,sp_res,csv_file=None,Regu=None,method='DT',args=None,res_calc_freq=1):

    from Tucker.common_kernels import get_residual_sp, get_residual
    from Tucker.standard_ALS import Tucker_DTALS_Optimizer, Tucker_PPALS_Optimizer

    if csv_file is not None:
        csv_writer = csv.writer(
            csv_file, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)

    time_all = 0.
    optimizer_list = {
        'DT': Tucker_DTALS_Optimizer(tenpy,T,A),
        'PP': Tucker_PPALS_Optimizer(tenpy,T,A,args),
    }
    optimizer = optimizer_list[method]

    normT = tenpy.vecnorm(T)

    for i in range(num_iter):
        if i % res_calc_freq == 0 or i==num_iter-1:
            if sp_res:
                # TODO: implement the get residual sparse version
                res = get_residual_sp(tenpy,O,T,optimizer.A)
            else:
                res = get_residual(tenpy,T,optimizer.A)
            fitness = 1-res/normT

            if tenpy.is_master_proc():
                print("[",i,"] Residual is", res, "fitness is: ", fitness)
                # write to csv file
                if csv_file is not None:
                    csv_writer.writerow([i, time_all, res, fitness])
                    csv_file.flush()
        t0 = time.time()
        A = optimizer.step(Regu)
        t1 = time.time()
        tenpy.printf("Sweep took", t1-t0,"seconds")
        time_all += t1-t0
    tenpy.printf("Naive method took",time_all,"seconds overall")

    if args.save_tensor:
        folderpath = join(results_dir, arg_defs.get_file_prefix(args))
        save_decomposition_results(T,A,tenpy,folderpath)

    return res

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    arg_defs.add_general_arguments(parser)
    arg_defs.add_pp_arguments(parser)
    arg_defs.add_lrdt_arguments(parser)
    arg_defs.add_sparse_arguments(parser)
    arg_defs.add_nls_arguments(parser)
    arg_defs.add_col_arguments(parser)
    args, _ = parser.parse_known_args()

    # Set up CSV logging
    csv_path = join(results_dir, arg_defs.get_file_prefix(args)+'.csv')
    is_new_log = not Path(csv_path).exists()
    csv_file = open(csv_path, 'a')#, newline='')
    csv_writer = csv.writer(
        csv_file, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)

    s = args.s
    order = args.order
    R = args.R
    r = args.r
    nls_tol = args.nls_tol
    grad_tol = args.grad_tol
    cg_tol = args.cg_tol
    switch_tol = args.switch_tol
    nls_iter = args.nls_iter
    als_iter = args.als_iter
    num = args.num
    num_iter = args.num_iter
    num_lowr_init_iter = args.num_lowr_init_iter
    sp_frac = args.sp_fraction
    sp_res = args.sp_res
    tensor = args.tensor
    maxiter = args.maxiter
    tlib = args.tlib
    own_cg = args.own_cg

    if tlib == "numpy":
        import backend.numpy_ext as tenpy
    elif tlib == "ctf":
        import backend.ctf_ext as tenpy
        import ctf
        tepoch = ctf.timer_epoch("ALS")
        tepoch.begin();

    if tenpy.is_master_proc():
        # print the arguments
        for arg in vars(args) :
            print( arg+':', getattr(args, arg))
        # initialize the csv file
        if is_new_log:
            csv_writer.writerow([
                'iterations', 'time', 'residual', 'fitness'
            ])

    tenpy.seed(args.seed)

    if args.load_tensor is not '':
        T = tenpy.load_tensor_from_file(args.load_tensor+'tensor.npy')
        O = None
    elif tensor == "random":
        if args.decomposition == "CP":
            tenpy.printf("Testing random tensor")
            [T,O] = synthetic_tensors.init_rand(tenpy,order,s,R,sp_frac,args.seed)
        if args.decomposition == "Tucker":
            tenpy.printf("Testing random tensor")
            shape = s * np.ones(order).astype(int)
            T = tenpy.random(shape)
            O = None
    elif tensor == "random_col":
        [T,O] = synthetic_tensors.init_collinearity_tensor(tenpy, s, order, R, args.col, args.seed)
    elif tensor == "mom_cons":
        tenpy.printf("Testing order 4 momentum conservation tensor")
        T = synthetic_tensors.init_mom_cons(tenpy,s)
        O = None
        sp_res = False
    elif tensor == "mom_cons_sv":
        tenpy.printf("Testing order 3 singular vectors of unfolding of momentum conservation tensor")
        T = synthetic_tensors.init_mom_cons_sv(tenpy,s)
        O = None
        sp_res = False
    elif tensor == "amino":
        T = real_tensors.amino_acids(tenpy)
        O = None
    elif tensor == "coil100":
        T = real_tensors.coil_100(tenpy)
        O = None
    elif tensor == "timelapse":
        T = real_tensors.time_lapse_images(tenpy)
        O = None
    elif tensor == "scf":
        T = real_tensors.get_scf_tensor(tenpy)
        O = None
    elif tensor == "embedding":
        T = real_tensors.get_bert_embedding_tensor(tenpy)
        O = None
    elif tensor == "bert-param":
        T = real_tensors.get_bert_weights_tensor(tenpy)
        O = None
    elif tensor == "mm":
        tenpy.printf("Testing matrix multiplication tensor")
        [T,O] = synthetic_tensors.init_mm(tenpy,s,R,args.seed)
    elif tensor == "negrandom":
        tenpy.printf("Testing random tensor with negative entries")
        [T,O] = synthetic_tensors.init_neg_rand(tenpy,order,s,R,sp_frac,args.seed)
        
    tenpy.printf("The shape of the input tensor is: ", T.shape)

    Regu = args.regularization

    A = []
    if args.load_tensor is not '':
        for i in range(T.ndim):
            A.append(tenpy.load_tensor_from_file(args.load_tensor+'mat'+str(i)+'.npy'))
    elif args.hosvd != 0:
        if args.decomposition == "CP":
            for i in range(T.ndim):
                A.append(tenpy.random((args.hosvd_core_dim[i],R)))
        elif args.decomposition == "Tucker":
            from Tucker.common_kernels import hosvd
            A = hosvd(tenpy, T, args.hosvd_core_dim, compute_core=False)
    else:
        for i in range(T.ndim):
            A.append(tenpy.random((T.shape[i],R)))

    if args.decomposition == "CP":
        # TODO: it doesn't support sparse calculation with hosvd here
        CP_ALS(tenpy,A,T,O,num_iter,sp_res,csv_file,Regu,args.method,args.hosvd,args, args.res_calc_freq,nls_tol,cg_tol,grad_tol,num,switch_tol,own_cg,nls_iter, als_iter,maxiter)
    elif args.decomposition == "Tucker":
        Tucker_ALS(tenpy,A,T,O,num_iter,sp_res,csv_file,Regu,args.method,args,args.res_calc_freq)
    if tlib == "ctf":
        tepoch.end()
