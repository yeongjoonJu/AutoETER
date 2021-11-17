python codes/run.py --cuda --do_train --do_valid --do_test --data_path data/FB15k --model AutoETER -n 128 -b 1024 -d 1000  -td 200 -g 22.0 -gt 8.0 -gp 6.0 -al1 0.1 -al2 0.5 -a 1.0 -lr 0.0001 --max_steps 300000 -save models/AutoETER_fb15k_4 -ps 16 -de --log_steps 5000 --valid_steps 15000 --multi_path

