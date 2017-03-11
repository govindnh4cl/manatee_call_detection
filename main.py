import os
import numpy as np
from scipy.io import loadmat
import matplotlib.pyplot as plt
import eval

val_type = '25s'

def lms(x, m, lr):
    N = x.shape[0]
    e = np.zeros(N)
    J = np.zeros(N)
    x_pred = np.zeros(N)
    w_n = np.zeros(m)

    for i in range(m, N):
        x_n = x[i - m:i]
        x_pred[i] = np.dot(w_n, x_n)
        e[i] = x[i] - x_pred[i]
        J[i] = e[i] ** 2
        w_n = w_n + lr * e[i] * x_n

    # Reversing w so that first entries represent coefficients
    # that are closest in time domain from current samples
    # print(np.flip(w_n, axis=0))

    return w_n, x_pred, J

def smooth(x):
    box_pts = 100
    box = np.ones(box_pts)/box_pts
    x_smooth = np.convolve(x, box, mode='same')
    return x_smooth

def detect_manatee(x, w_call, w_noise):
    m = w_call.shape[0]
    N = x.shape[0]
    e = np.zeros(N)
    J_call = np.zeros(N)
    J_noise = np.zeros(N)
    x_pred_call = np.zeros(N)
    x_pred_noise = np.zeros(N)

    for i in range(m, N):
        x_pred_call[i] = np.dot(w_call, x[i - m:i])
        x_pred_noise[i] = np.dot(w_noise, x[i - m:i])

    J_call = (x_pred_call - x) ** 2
    J_noise = (x_pred_noise - x) ** 2
    J_call = smooth(J_call)
    J_noise = smooth(J_noise)
    return J_call, J_noise

def train_filter(filter_order):
    # Load train signal
    with open(r'resources\train_signal.npy', 'rb') as f:
        train_signal = np.load(f)
    with open(r'resources\noise_signal.npy', 'rb') as f:
        noise_signal = np.load(f)

    w_train, x_train, J_train = lms(train_signal, filter_order, 0.01)
    # plt.plot(x_train)

    w_noise, x_noise, J_noise = lms(noise_signal, filter_order, 0.01)
    # plt.plot(x_noise)

    return w_train, w_noise

def run_validation_set(w_train, w_noise, val_type):
    print('Loading validation data...')
    if val_type is '75s':
        with open(r'resources\validation_75s.npy', 'rb') as f:
            x = np.load(f)
        with open(r'resources\ground_truth_val_75s.npy', 'rb') as f:
            dict = np.load(f).item()
            low = dict['low']
            high = dict['high']
    else:
        with open(r'resources\validation_25s.npy', 'rb') as f:
            x = np.load(f)
        with open(r'resources\ground_truth_val_25s.npy', 'rb') as f:
            dict = np.load(f).item()
            low = dict['low']
            high = dict['high']

    print('Detecting manatee calls...')
    J_call, J_noise = detect_manatee(x, w_train, w_noise)
    # eval.plot_cost(J_call)
    # eval.plot_cost(J_noise)
    J_diff = J_noise - J_call

    # eval.plot_calls(J_diff)

    if 0:
        acc = eval.get_accuracy(J_diff, low, high)

    if 1:
        eval.get_pr_curve(J_diff, low, high)

def run_test_set(w_train, w_noise, get_auc=False):
    acc = auc = -1

    with open(r'resources\test_signal.npy', 'rb') as f:
        x = np.load(f)
    with open(r'resources\ground_truth_test.npy', 'rb') as f:
        dict = np.load(f).item()
    with open(r'resources\ground_truth_test_signal.npy', 'rb') as f:
        dict_signal = np.load(f).item()

    if 1:
        gt_low = dict['low'][dict['idx_regular']]
        gt_high = dict['high'][dict['idx_regular']]
        gt_signal = dict_signal['regular']
    else:
        gt_low = dict['low'][dict['idx_all']]
        gt_high = dict['high'][dict['idx_all']]
        gt_signal = dict_signal['all']

    J_call, J_noise = detect_manatee(x, w_train, w_noise)
    # eval.plot_cost(J_call)
    # eval.plot_cost(J_noise)
    J_diff = J_noise - J_call

    if 0:
        eval.plot_calls(J_diff)

    if 0:
        acc = eval.get_accuracy(J_diff, gt_low, gt_high)

    if 0:
        eval.get_pr_curve(J_diff, gt_low, gt_high)

    if 1:
        dict_roc = eval.get_roc_curve(J_diff, gt_signal, plot_curve=False)
        auc = dict_roc['auc']

    test_result = {'auc': auc, 'acc': acc}
    return test_result

if __name__ == '__main__':
    filter_orders = [15] # [1, 2, 4, 7, 10, 15, 20, 35, 50]
    plot_auc = True

    auc = np.empty(len(filter_orders))

    for i, filter_order in enumerate(filter_orders):
        w_train = w_noise = None
        weights_file = r'resources\lms_weights_w'+str(filter_order)+'.npy'
        if os.path.exists(weights_file):
            print('Filter order: {0:d} Getting stored weights...'.format(filter_order))
            with open(weights_file, 'rb') as f:
                dict = np.load(f).item()
            w_train = dict['w_train']
            w_noise = dict['w_noise']
        else:
            print('Filter order: {0:d} Computing weights...'.format(filter_order))
            w_train, w_noise = train_filter(filter_order)
            weights = {'w_train': w_train, 'w_noise': w_noise}
            np.save(weights_file, weights)

        # Parameter tuning using a validation set
        if 0:
            run_validation_set(w_train, w_noise, val_type)

        # Testing
        if 0:
            run_test_set(w_train, w_noise)

        # Testing while plotting AUC
        if plot_auc:
            test_result = run_test_set(w_train, w_noise, get_auc=True)
            auc[i] = test_result['auc']

    if plot_auc:
        plt.figure()
        lw = 2 #linewidth
        plt.plot(filter_orders, auc, color='red',lw=lw)
        plt.xlim([1, max(filter_orders)])
        plt.ylim([0.0, 1.05])
        plt.xlabel('Filter Order')
        plt.ylabel('AUC')
        plt.title('AUC vs Filter Order')
        plt.show()