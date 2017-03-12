import os
import numpy as np
from scipy.io import loadmat
import matplotlib.pyplot as plt
import eval
import argparse

from keras.models import Sequential, Model, load_model
from keras.layers import Input, Convolution1D, MaxPooling1D, Dense, Flatten, Lambda, Merge
from keras.optimizers import RMSprop
from keras.callbacks import ModelCheckpoint

val_type = '25s'
default_store_model = 'model.h5'

def smooth(x):
    box_pts = 100
    box = np.ones(box_pts)/box_pts
    x_smooth = np.convolve(x, box, mode='same')
    return x_smooth

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

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", help="train/test")
    parser.add_argument("--model", help="model to be stored/read")
    parser.add_argument("--epochs", help="#epochs while training")
    args = parser.parse_args()

    if not args.phase:
        parser.print_help()
        parser.error('Must specify phase (train/test)')
    elif args.phase not in ['train', 'test']:
        parser.print_help()
        parser.error('phase must be (train/test)')

    if args.phase == 'train':
        args.epochs = int(args.epochs)

    if not args.model:
        print('No model specified. using default: ', default_store_model)
        args.model = default_store_model
    return args

def create_model(window_size):
    input_shape = (window_size, 1)
    model = Sequential()
    model.add(Convolution1D(8, 5, activation='relu', border_mode='valid', input_shape=input_shape))
    # model.add(Convolution1D(16, 5, activation='relu', border_mode='valid'))
    # model.add(Convolution1D(32, 5, activation='relu', border_mode='valid'))
    # model.add(Convolution1D(64, 5, activation='relu', border_mode='valid'))
    model.add(Flatten())
    model.add(Dense(512, activation='sigmoid'))
    model.add(Dense(1, activation='sigmoid'))
    return model

def dump_history(history, log_file_name, val_set_present):
    f = open(log_file_name, "w")

    train_acc = history['acc']
    train_loss = history['loss']

    if val_set_present:
        val_acc = history['val_acc']
        val_loss = history['val_loss']
    else:
        val_acc = [-1] * len(train_acc)
        val_loss = val_acc

    f.write('Epoch  Train_loss  Train_acc  Val_loss  Val_acc  \n')

    for i in range(len(train_acc)):
        f.write('{0:d} {1:.2f} {2:.2f}% {3:.2f} {4:.2f}%\n'.format(
            i, train_loss[i], 100 * train_acc[i], val_loss[i], 100 * val_acc[i]))

    print('Dumped history to file: {0:s}'.format(log_file_name))

def get_batch(x_full, gt_full, window_size, stride_size, batch_size):
    x = np.empty([batch_size, window_size, 1])
    y = np.empty(batch_size)
    x_idx = 0
    i = 0

    while 1:
        if x_idx + window_size < len(x_full):
            x[i] = x_full[x_idx:x_idx+window_size].reshape(window_size, 1)
            gt = gt_full[x_idx:x_idx+window_size]
            y[i] = np.any(gt == 1)
            i += 1
            x_idx += stride_size
            if i == batch_size:
                i = 0
                yield (x, y)
        else:
            x_idx = 0

def train_net(cfg, x, gt_signa):
    batch_size = cfg['batch_size']
    window_size = cfg['window_size']
    stride_size = window_size
    model = create_model(window_size)
    rms = RMSprop() # Optimizer
    model.compile(loss='binary_crossentropy', optimizer=rms, metrics=['accuracy'])

    # Create check point callback
    checkpointer = ModelCheckpoint(
        filepath=cfg['model_file'],
        monitor='loss', verbose=1, save_best_only=True)

    num_train_sample = int(len(x)/stride_size)

    hist = model.fit_generator(
        get_batch(x, gt_signal, window_size, stride_size, batch_size),
        samples_per_epoch=num_train_sample,
        nb_epoch=cfg['epochs'],
        callbacks=[checkpointer])

    dump_history(hist.history, 'history.log', val_set_present=False)
    print('Training complete. Saved model as: ', cfg['model_file'])

def test_net(cfg, x_test, gt_signal):
    batch_size = cfg['batch_size']
    window_size = cfg['window_size']
    stride_size = window_size

    model = load_model(cfg['model_file'])

    num_batches = int(np.ceil(len(x_test)/stride_size + batch_size - 1)/batch_size)
    gen = get_batch(x_test, gt_signal, window_size, stride_size, batch_size)

    y_array = np.zeros(num_batches * batch_size)
    y_pred_array = np.zeros(y_array.shape)
    idx = 0

    for i in range(num_batches):
        print("\rPredicting batch id: {0:d}/{1:d}".format(i, num_batches-1), end='')
        x, y = next(gen)
        y_pred = model.predict_on_batch(x)
        y_array[i:i+batch_size] = y
        y_pred_array[i:i+batch_size] = y_pred.reshape(batch_size)
        i += batch_size
    print('\n')

    if 1:
        dict_roc = eval.get_roc_curve(y_pred_array, y_array, plot_curve=True)
        auc = dict_roc['auc']

if __name__ == '__main__':
    args = parse_arguments()

    cfg = {}
    cfg['model_file'] = args.model
    cfg['window_size'] = 100

    if args.phase == 'train':
        cfg['epochs'] = args.epochs
        cfg['batch_size'] = 32
        with open(r'resources\validation_25s.npy', 'rb') as f:
            x = np.load(f)
        with open(r'resources\ground_truth_val_25s_signal.npy', 'rb') as f:
            gt_signal = np.load(f)

        train_net(cfg, x, gt_signal)
    else:
        cfg['batch_size'] = 32

        with open(r'resources\test_signal.npy', 'rb') as f:
            x_test = np.load(f)
        with open(r'resources\ground_truth_test_signal.npy', 'rb') as f:
            gt_signal = np.load(f).item()['regular']

        test_net(cfg, x_test, gt_signal)



