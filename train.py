import argparse
from torch import nn, optim
from vae import *
from loss import *
from dataloader import *


parser = argparse.ArgumentParser()
parser.add_argument("--batch_size", help="echo the string you use here", type=int, default=256)
parser.add_argument("--epochs_estim", help="epochs for estimator network", type=int, default=9)
parser.add_argument("--epochs_vae", help="epochs for VAE", type=int, default=1000)
parser.add_argument("--epochs_pred", help="epochs for predictor network", type=int, default=350)
parser.add_argument("--seed", help="random seed", type=int, default=9)
parser.add_argument("--log_interval", help="number batches to wait before logging training status", type=int, default=10)
parser.add_argument("--latent_dim", help="VAE latent space dimension", type=int, default=15)
parser.add_argument("--gauss_mix", help="uses Gaussian mixture prior if specified", action='store_true')
parser.add_argument("--num_gauss", help="number of Gaussian components in mixture prior", type=int, default=14)
parser.add_argument("--num_flows", help="number of spline autoregressive flows to use in VAE", type=int, default=3)
parser.add_argument("--num_blocks_estim", help="number of residual/ODE blocks to use in estimator network", type=int, default=3)
parser.add_argument("--num_blocks_pred", help="number of residual/ODE blocks to use in VAE", type=int, default=3)
parser.add_argument("--num_blocks_vae", help="number of residual/ODE blocks to use in predictor network", type=int, default=3)
parser.add_argument("--dropout_estim", help="dropout probability in estimator network", type=int, default=0.3)
parser.add_argument("--dropout_pred", help="dropout probability in predictor network", type=int, default=0.3)
parser.add_argument("--dropout_vae", help="dropout probability in VAE encoder/decoder", type=int, default=0.3)
parser.add_argument("--tol", help="ODE solver tolerance", type=int, default=1e-3)
parser.add_argument("--lr", help="learning rate", type=int, default=1e-5)
parser.add_argument("--data_loc", help="data location on drive", default=r'/home/taymaz/Downloads/MP.npy')
parser.add_argument("--network_type", help="ResNet or neuralODE", default="ResNet", choices=['ResNet', 'neuralODE'])
parser.add_argument("--no_cuda", help="uses CUDA if specified", action='store_false')
args = parser.parse_args()


# initialise CUDA
if args.no_cuda:
    device = torch.device("cpu")
    torch.set_default_tensor_type("torch.FloatTensor")
else:
    device = torch.device("cuda")
    torch.set_default_tensor_type("torch.cuda.FloatTensor")
    torch.cuda.empty_cache()
torch.manual_seed(args.seed)


# instantiate models
if args.network_type == "neuralODE":

    structural_estimator_model = ODEnet(3600, 14, int((3600+14)/2), num_blocks=args.num_blocks_estim, tol=args.tol, dropout=args.dropout_estim)
    structural_estimator_optimizer = optim.Adam(structural_estimator_model.parameters(), lr=args.lr)

    structural_estimator_model = ODEnet(3600, 14, int((3600+14)/2), num_blocks=args.num_blocks_estim, tol=args.tol, dropout=args.dropout_estim)
    structural_estimator_optimizer = optim.Adam(structural_estimator_model.parameters(), lr=args.lr)

    energetic_estimator_model = ODEnet(3600, 1, int(3600 / 2), num_blocks=args.num_blocks_estim, tol=args.tol, dropout=args.dropout_estim)
    energetic_estimator_optimizer = optim.Adam(energetic_estimator_model.parameters(), lr=args.lr)

    predictor_model = ODEnet(args.latent_dim, 1, int((args.latent_dim)/2), num_blocks=args.num_blocks_pred, dropout=args.dropout_pred)
    predictor_optimizer = optim.Adam(predictor_model.parameters(), lr=args.lr)

    vae_model = FlowVAE(input_dim=3600,hidden_dim=200,latent_dim=args.latent_dim, num_blocks=args.num_blocks_vae, num_flows=args.num_flows, dropout=args.dropout_vae, gauss_mix=args.gauss_mix, num_gauss=args.num_gauss, network='odenet').to(device)
    vae_optimizer = optim.Adam(vae_model.parameters(), lr=1e-5)

if args.network_type == "ResNet":

    structural_estimator_model = ResidualNet(3600, 14, int((3600 + 14) / 2), num_blocks=args.num_blocks_estim, dropout=args.dropout_estim)
    structural_estimator_optimizer = optim.Adam(structural_estimator_model.parameters(), lr=args.lr)

    structural_estimator_model = ResidualNet(3600, 14, int((3600 + 14) / 2), num_blocks=args.num_blocks_estim, dropout=args.dropout_estim)
    structural_estimator_optimizer = optim.Adam(structural_estimator_model.parameters(), lr=args.lr)

    energetic_estimator_model = ResidualNet(3600, 1, int(3600 / 2), num_blocks=args.num_blocks_estim, dropout=args.dropout_estim)
    energetic_estimator_optimizer = optim.Adam(energetic_estimator_model.parameters(), lr=args.lr)

    predictor_model = ResidualNet(args.latent_dim, 1, int((args.latent_dim) / 2), num_blocks=args.num_blocks_pred, dropout=args.dropout_pred)
    predictor_optimizer = optim.Adam(predictor_model.parameters(), lr=args.lr)

    vae_model = FlowVAE(input_dim=3600,hidden_dim=200,latent_dim=args.latent_dim, num_blocks=args.num_blocks_vae, num_flows=args.num_flows, dropout=args.dropout_vae, gauss_mix=args.gauss_mix, num_gauss=args.num_gauss, network='resnet').to(device)
    vae_optimizer = optim.Adam(vae_model.parameters(), lr=1e-5)


# define epoch based structural trainer
def structural_estimator_train(epoch):
    structural_estimator_model.train()
    matches = 0
    for batch_idx, (data, tar_energy, tar_structure) in enumerate(train_loader):
        data = data.to(device)
        tar = tar_structure.view(-1, 1).to(torch.long).to(device)
        structural_estimator_optimizer.zero_grad()
        tar_pred = structural_estimator_model(data)
        loss = pred_loss_CE(tar, tar_pred)
        loss.backward()
        structural_estimator_optimizer.step()
        matches += num_matches(tar, tar_pred).item()
    return loss

# define epoch based structural tester
def structural_estimator_test(epoch):
    structural_estimator_model.eval()
    matches = 0
    with torch.no_grad():
        for batch_idx, (data, tar_energy, tar_structure) in enumerate(val_loader_1):
            data = data.to(device)
            tar = tar_structure.view(-1, 1).to(torch.long).to(device)
            structural_estimator_optimizer.zero_grad()
            tar_pred = structural_estimator_model(data)
            loss = pred_loss_CE(tar, tar_pred)
            matches += num_matches(tar, tar_pred).item()
            if batch_idx % args.log_interval == 0:
                print(f'Epoch:{epoch}, pre-train val prediction loss: {loss.item()}')
    return loss

# define epoch based energetic trainer
def energetic_estimator_train(epoch):
    energetic_estimator_model.train()
    matches = 0
    for batch_idx, (data, tar_energy, tar_structure) in enumerate(train_loader):
        data = data.to(device)
        tar = tar_energy.view(-1, 1).to(device)
        energetic_estimator_optimizer.zero_grad()
        tar_pred = energetic_estimator_model(data)
        loss = pred_loss_MSE(tar, tar_pred)
        loss.backward()
        energetic_estimator_optimizer.step()
        matches += num_matches(tar, tar_pred).item()
    return loss

# define epoch based energetic tester
def energetic_estimator_test(epoch):
    energetic_estimator_model.eval()
    matches = 0
    with torch.no_grad():
        for batch_idx, (data, tar_energy, tar_structure) in enumerate(val_loader_1):
            data = data.to(device)
            tar = tar_energy.view(-1, 1).to(device)
            energetic_estimator_optimizer.zero_grad()
            tar_pred = energetic_estimator_model(data)
            loss = pred_loss_MSE(tar, tar_pred)
            matches += num_matches(tar, tar_pred).item()
            if batch_idx % args.log_interval == 0:
                print(f'Epoch:{epoch}, pre-train val prediction loss: {loss.item()}')
    return loss

# define epoch based VAE trainer
def vae_train(epoch):
    vae_model.train()
    latent = []
    for batch_idx, (data, tar_energy, tar_structure) in enumerate(train_loader):
        data = data.to(device)
        tar_structure = tar_structure.view(-1, 1).to(torch.long).to(device)
        tar_energy = tar_energy.view(-1, 1).to(device)
        vae_optimizer.zero_grad()
        x_pred, mu, logvar, _, energetic_embed = vae_model(data, tar_structure, tar_energy)
        latent.append(energetic_embed.detach().cpu().numpy())
        loss, _, _ = vae_loss(x_pred, data, mu, logvar)
        loss.backward()
        vae_optimizer.step()
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\t Total Loss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                       100. * batch_idx / len(train_loader),
                       loss.item() / len(data)))
    return loss, latent

# define epoch based VAE tester
def vae_test(epoch):
    vae_model.eval()
    with torch.no_grad():
        for i, (data, tar_energy, tar_structure) in enumerate(val_loader_1):
            data = data.to(device)
            tar_structure = tar_structure.view(-1, 1).to(torch.long).to(device)
            tar_energy = tar_energy.view(-1, 1).to(device)
            vae_optimizer.zero_grad()
            x_pred, mu, logvar, _, _ = vae_model(data, tar_structure, tar_energy)
            loss, _, _ = vae_loss(x_pred, data, mu, logvar)
    return loss

# define epoch based predictor trainer
def pred_train(epoch):
    structural_estimator_model.eval()
    energetic_estimator_model.eval()
    vae_model.eval()
    predictor_model.train()
    latent = []
    matches = 0
    for batch_idx, (data, tar_energy, tar_structure) in enumerate(val_loader_1_training):
        data = data.to(device)
        context_structure = structural_estimator_model(data).argmax(dim=1).view(-1, 1)
        context_energy = energetic_estimator_model(data).argmax(dim=1).view(-1, 1)
        _, _, _, _, energetic_embedding = vae_model(data, context_structure, context_energy)
        tar_structure = tar_structure.view(-1, 1).to(torch.long).to(device)
        tar_energy = tar_energy.view(-1, 1).to(device)
        predictor_optimizer.zero_grad()
        pred_energy = predictor_model(energetic_embedding)
        latent.append(energetic_embedding.detach().cpu().numpy())
        loss = pred_loss_MSE(tar_energy, pred_energy)
        loss.backward()
        predictor_optimizer.step()
        # matches += num_matches(tar_energy, pred_energy).item()
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\t Total Loss: {:.6f}'.format(
                epoch, batch_idx * len(data), len(train_loader.dataset),
                       100. * batch_idx / len(train_loader),
                       loss.item() / len(data)))
    return loss, latent

# define epoch based predictor tester
def pred_test(epoch):
    structural_estimator_model.eval()
    energetic_estimator_model.eval()
    vae_model.eval()
    predictor_model.eval()
    latent = []
    matches = 0
    with torch.no_grad():
        for batch_idx, (data, tar_energy, tar_structure) in enumerate(val_loader_2):
            data = data.to(device)
            context_structure = structural_estimator_model(data).argmax(dim=1).view(-1, 1)
            context_energy = energetic_estimator_model(data).argmax(dim=1).view(-1, 1)
            _, _, _, _, energetic_embedding = vae_model(data, context_structure, context_energy)
            tar_structure = tar_structure.view(-1, 1).to(torch.long).to(device)
            tar_energy = tar_energy.view(-1, 1).to(device)
            predictor_optimizer.zero_grad()
            pred_energy = predictor_model(energetic_embedding)
            latent.append(energetic_embedding.detach().cpu().numpy())
            loss = pred_loss_MSE(tar_energy, pred_energy)
            # matches += num_matches(tar, tar_pred).item()
    return loss


# load data
train_loader, val_loader_1, val_loader_2 = material_loader(args.data_loc, args.batch_size)


# train
struc_estim_train_loss_list = []
struc_estim_test_loss_list = []
for epoch in range(1, args.epochs_estim + 1):
    train_loss = structural_estimator_train(epoch)
    test_loss= structural_estimator_test(epoch)
    struc_estim_train_loss_list.append(train_loss.cpu().detach().numpy())
    struc_estim_test_loss_list.append(test_loss.cpu().detach().numpy())
print('structural estimator training done')

energ_estim_train_loss_list = []
energ_estim_test_loss_list = []
for epoch in range(1, args.epochs_estim + 1):
    train_loss = energetic_estimator_train(epoch)
    test_loss = energetic_estimator_test(epoch)
    energ_estim_train_loss_list.append(train_loss.cpu().detach().numpy())
    energ_estim_test_loss_list.append(test_loss.cpu().detach().numpy())
print('energy estimator training done')

vae_train_loss_list = []
vae_test_loss_list = []
latent_list = []
for epoch in range(1, args.epochs_vae + 1):
    train_loss, latent = vae_train(epoch)
    test_loss = vae_test(epoch)
    vae_train_loss_list.append(train_loss.cpu().detach().numpy())
    vae_test_loss_list.append(test_loss.cpu().detach().numpy())
    latent_list.append(latent)
print('latent space training done')

pred_train_loss_list = []
pred_test_loss_list = []
pred_latent_list = []
for epoch in range(1, args.epochs_pred + 1):
    train_loss, latent = pred_train(epoch)
    test_loss = pred_test(epoch)
    pred_train_loss_list.append(train_loss.cpu().detach().numpy())
    pred_test_loss_list.append(test_loss.cpu().detach().numpy())
    pred_latent_list.append(latent)
print('predictor training done')


# save results
np.save('struc_estim_train_loss_list', struc_estim_train_loss_list)
np.save('struc_estim_test_loss_list', struc_estim_test_loss_list)
np.save('energ_estim_train_loss_list', energ_estim_train_loss_list)
np.save('energ_estim_test_loss_list', energ_estim_test_loss_list)
np.save('vae_train_loss_list', vae_train_loss_list)
np.save('vae_test_loss_list', vae_test_loss_list)
np.save('latent_list', latent_list)
np.save('pred_train_loss_list', pred_train_loss_list)
np.save('pred_test_loss_list', pred_test_loss_list)
np.save('pred_latent_list', pred_latent_list)
