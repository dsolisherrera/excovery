import matplotlib as mpl
import matplotlib.pyplot as plt
from collections import defaultdict
from matplotlib.backends.backend_pdf import PdfPages
from mpl_toolkits.axes_grid.axislines import Subplot
import sqlite3
import datetime

def db_timestamp_to_datetime(db_timestamp):
	dt, _, us= db_timestamp.partition(".")
	dt= datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
	if (us == ''):
		us = 0
	else:
		us= int(us.rstrip("Z"), 10)
	return  dt + datetime.timedelta(microseconds=us)

def modifyCommonTimeDatabase(database,delta_hours):
	new_rows = []
	db = sqlite3.connect(database)
	c = db.cursor()
	c.execute("SELECT * FROM packets")
	
	rows = c.fetchall()
	
	for x in rows:
		p = list(x)
		db_timestamp = p[2]
		dt, _, us= db_timestamp.partition(".")
		dt= datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
		if (us == ''):
			us = 0
		else:
			us= int(us.rstrip("Z"), 10)
		pd =  dt + datetime.timedelta(microseconds=us) + datetime.timedelta(hours = delta_hours)
		p[2] = pd
		p[2] = unicode(p[2])
		new_rows.append(p)

	c.execute("DELETE FROM packets")
	for x in new_rows:
		c.execute("INSERT INTO Packets (RunID,NodeID,CommonTime, SrcNodeId, Data) VALUES (?,?,?,?,?)", [x[0],x[1],x[2],x[3],x[4]])
	db.commit()

def majority_vote(A):
    min = len(A)/2.0
    counts = {}
    for x in A:
        if x in counts:
            counts[x] += 1
        else:
            counts[x] = 1
    a = max(counts.iteritems(), key = lambda x: x[1])
    if a[1] > min:
        return a[0]
    else:
        return a[0]

def moving_average(x, n, typ='simple'):
    """
    compute an n period moving average.
    type is 'simple' | 'exponential'
    """
    x = np.asarray(x)
    if typ=='simple':
        weights = np.ones(n)
    else:
        weights = np.exp(np.linspace(-1., 0., n))

    weights /= weights.sum()

    a =  np.convolve(x, weights, mode='full')[:len(x)]
    a[:n] = a[n]
    return a

def reduceArray_toClosest_approx(source_x,source_y, objective_x, objective_y,deadline):
    
	red_source_x = []
	red_source_y = []
	last_val = -1

	#Reduce size of source array by eliminating duplicate values and timeouts, this reduces the resolution of the
	# results.
	for val in source_x:
		if val != last_val and val <= deadline:
			pos = source_x.index(val)
			red_source_x.append(val)
			red_source_y.append(source_y[pos])
			last = val
    
	approx_source_x = []
	approx_source_y = []

	for obj_val in objective_x:
		first_val = True
		min_diff = 10000 #arbitrarly big number
		
		for src_val in red_source_x:
			diff = abs(src_val - obj_val)
			if diff < min_diff:
				pos = red_source_x.index(src_val)
				min_diff = diff
				
				min_x_val = src_val
				min_y_val = red_source_y[pos]
		approx_source_x.append(min_x_val)
		approx_source_y.append(min_y_val)
	return (approx_source_x,approx_source_y)


def print_plot_cdf(figures,fig,ax,xdata,ydata,xscale,deadline,data_num,use_grid,database_name=None,legend=None,bw_value=None):
	
    colors=['black','red','gray','green','green','purple','blue','cyan','brown','magenta']
    linestyles=['-',':','-.','--','-.',':','-.','--','-',':','--','-.']
    markers=['None','None','None','None','+','*','x','^','v','<','>']

    if (legend == None):
        fn_split=database_name.split("_")

        if fn_split[-2].lower() == 'power':
            legend_string = fn_split[-1] + ' dB'
        
        elif len(fn_split) < 3:
            legend_string = "Load %.2f Mbit/s" % (float(bw_value)*10/1024)
        
        elif fn_split[2].lower() != 'load':
            legend_string = fn_split[2]

        else:
            if int(fn_split[3]) > 0:
                legend_string = "%d VoIP Streams Load" % int(fn_split[3])
            else:
                legend_string = "No Load"
    else:
        legend_string = legend
	
    ax.xaxis.set_major_locator(ScaledLocator(dx=xscale))
    ax.xaxis.set_major_formatter(ScaledFormatter(dx=xscale))
    ax.axis["right"].set_visible(False)
    ax.axis["top"].set_visible(False)

    ax.plot(xdata, ydata, drawstyle='steps-post',linestyle=linestyles[data_num], marker=markers[data_num],color=colors[data_num], label=legend_string)
    ax.set_xlabel('Deadline in s',{'fontsize':'x-large'})
    ax.set_ylabel('Responsiveness',{'fontsize':'x-large'})
    if (ydata[-1] < 0.6):
        ax.legend(loc = "upper right")
    elif (ydata[-1] > 0.6) and (abs(ydata[-1]-0.6) < 0.2):
        ax.legend(loc = "lower right")
    else:
        ax.legend(loc = "center right")
    ax.legend(loc = "center right")
    if (use_grid):
        ax.grid(use_grid)
    ax.set_ylim([0,1])
    ax.set_xlim([0,deadline])
    ax.hold(True)
    if fig not in figures:
        figures.append(fig)

def print_plot_pdf(figures,fig,ax,data,bins,weights,xscale,deadline,data_num,use_grid,database_name=None,legend=None,bw_value=None):
        
	colors=['black','red','blue','green','yellow','purple','gray','cyan','brown','magenta']
		
	if (legend == None):
		fn_split=database_name.split("_")
		if len(fn_split) < 3:
			legend_string = "Load %.2f Mbit/s" % (float(bw_value)*10/1024)
		
		elif fn_split[2].lower() != 'load':
			legend_string = fn_split[2]
		else:
			if int(fn_split[3]) > 0:
				legend_string = "%d VoIP Streams Load" % int(fn_split[3])
			else:
				legend_string = "No Load"
	else:
		legend_string = legend

	ax.xaxis.set_major_locator(ScaledLocator(dx=xscale))
	ax.xaxis.set_major_formatter(ScaledFormatter(dx=xscale))
	ax.axis["right"].set_visible(False)
	ax.axis["top"].set_visible(False)

	ax.hist(data, bins=bins, normed=False, weights=weights, histtype='stepfilled',color=colors[data_num], alpha=0.5,label=legend_string)
	ax.set_xlabel('Time in s',{'fontsize':'x-large'})
	ax.set_ylabel('Probability',{'fontsize':'x-large'})
	ax.legend(loc = "center right")

	if (use_grid):
		ax.grid(use_grid)
	ax.set_ylim([0,1])
	ax.set_xlim([0,deadline])
	ax.hold(True)
	if fig not in figures:
		figures.append(fig)

def print_plot_resp_load(figures,fig,ax,xdata,ydata,xscale,deadline,reg_line,provider,data_num,use_grid):
    
    colors=['black','gray','red','green','blue','purple','yellow','cyan','brown','magenta']
    linestyles=['-','-.',':','--',':','-.','-','--',':','-.']
    markers=['None','None','None','None','x','+','*','^','v','<','>']

    ax.xaxis.set_major_locator(ScaledLocator(dx=xscale))
    ax.xaxis.set_major_formatter(ScaledFormatter(dx=xscale))
    ax.axis["right"].set_visible(False)
    ax.axis["top"].set_visible(False)
    
    legend_string = "Provider " + provider
    
    if (not reg_line):
        ax.plot(xdata, ydata, linestyle='None', marker=markers[data_num + 4], color=colors[1],clip_on=False)
    else:
        ax.plot(xdata, ydata, linestyle=linestyles[data_num], color=colors[0],label=legend_string,clip_on=False)
        ax.legend(loc = "lower left")
    
    if (use_grid):
        ax.grid(use_grid)
    ax.set_xlabel('Number of VoIP streams',{'fontsize':'x-large'})
    ax.set_ylabel('Responsiveness',{'fontsize':'x-large'})
    
    ax.set_ylim([0,1])
    #ax.set_xlim([0,deadline])
    ax.hold(True)
    if fig not in figures:
        figures.append(fig)

def print_plot_resp_packetloss(figures,fig,ax,xdata,ydata,xscale,legend ,reg_line, plot_num, use_grid = True):
    
    colors=['black','gray','red','green','blue','purple','yellow','cyan','brown','magenta']
    linestyles=['-','-.',':','--',':','-.','-','--',':','-.']
    markers=['None','None','None','None','+','x','1','2','v','<','>']

    ax.xaxis.set_major_locator(ScaledLocator(dx=xscale))
    ax.xaxis.set_major_formatter(ScaledFormatter(dx=xscale))
    ax.axis["right"].set_visible(False)
    ax.axis["top"].set_visible(False)  
    
    if (not reg_line):
        ax.plot(xdata, ydata, linestyle='None', marker=markers[plot_num + 4], color=colors[0],clip_on=False)
    else:
        ax.plot(xdata, ydata, linestyle=linestyles[plot_num], color=colors[1],label=legend,clip_on=False)
        ax.legend(loc = "lower left")
    
    if (use_grid):
        ax.grid(use_grid)
    ax.set_xlabel('Packet loss rate in percentage',{'fontsize':'x-large'})
    ax.set_ylabel('Responsiveness',{'fontsize':'x-large'})
    
    ax.set_ylim([0,1])
    #ax.set_xlim([0,deadline])
    ax.hold(True)
    if fig not in figures:
		figures.append(fig)

def print_plot_resp_services(figures,fig,ax,xdata,ydata,xscale,reg_line,bw_id,use_grid,bw_value=None, legend = None):
	
	colors=['black','gray','red','green','blue','purple','yellow','cyan','brown','magenta']
	linestyles=['-','-.',':','--',':','-.','-','--',':','-.']
	markers=['None','None','None','None','+','x','1','2','v','<','>']

	ax.xaxis.set_major_locator(ScaledLocator(dx=xscale))
	ax.xaxis.set_major_formatter(ScaledFormatter(dx=xscale))
	ax.axis["right"].set_visible(False)
	ax.axis["top"].set_visible(False)
	if (legend == None):
		legend_string = "Load %.2f Mbit/s" % (float(bw_value)*10/1024)
	else:
		legend_string = legend

	if (not reg_line):
		ax.plot(xdata, ydata, linestyle='None', marker=markers[bw_id + 4], color=colors[0],clip_on=False)
	else:
		ax.plot(xdata, ydata, linestyle=linestyles[bw_id], color=colors[1],label=legend_string,clip_on=False)
		ax.legend(loc = "lower left")

	if (use_grid):
		ax.grid(use_grid)
	ax.set_xlabel('Number of Services',{'fontsize':'x-large'})
	ax.set_ylabel('Responsiveness',{'fontsize':'x-large'})

	ax.set_ylim([0,1])
	#ax.set_xlim([0,deadline])
	ax.hold(True)
	if fig not in figures:
		figures.append(fig)

def print_plot_resp_runs(figures,fig,ax,xdata,ydata,yscale,deadline,avg_line,level,data_num,use_grid,database_name=None,bw_value=None,legend=None):
    
	colors=['black','gray','red','green','blue','purple','yellow','cyan','brown','magenta']
	linestyles=['-','-.','-','--',':','-.','-','--',':','-.']
	markers=['None','None','None','None','+','*','.','x','^','v','<','>']

	if (legend == None):
		fn_split=database_name.split("_")
		if len(fn_split) < 3:
			legend_string = "Load %.2f Mbit/s" % (float(bw_value)*10/1024)
		
		elif fn_split[2].lower() != 'load':
			legend_string = fn_split[2]
		else:
			if int(fn_split[3]) > 0:
				legend_string = "%d VoIP Streams Load" % int(fn_split[3])
			else:
				legend_string = "No Load"
	else:
		legend_string = legend

	ax.yaxis.set_major_locator(ScaledLocator(dx=yscale))
	ax.yaxis.set_major_formatter(ScaledFormatter(dx=yscale))
	ax.axis["right"].set_visible(False)
	ax.axis["top"].set_visible(False)

	if (not avg_line):
		ax.plot(xdata, ydata, linestyle='None', marker = markers[6], markersize = 1,color=colors[1])
	else:
		ax.plot(xdata, ydata, linestyle=linestyles[0], color=colors[0],label=legend_string)
		ax.legend(loc = "upper right")
		
	if (use_grid):
		ax.grid(use_grid)
	ax.set_xlabel('Run Number',{'fontsize':'x-large'})
	ax.set_ylabel('Response Time in s',{'fontsize':'x-large'})

	if (level == 'events'):
		ax.set_ylim([0,20000])
	else:
		ax.set_ylim([0,1000])
	#ax.set_xlim([0,1000])
	ax.hold(True)
	if fig not in figures:
		figures.append(fig)

def print_plot_timediffs(figures,fig,ax,xdata,ydata,yscale,level,data_num,timediff_nodes,use_grid):
    
    colors=['black','red','blue','green','yellow','purple','gray','cyan','brown','magenta','#606063','#9B9BA1']
    linestyles=['-','-.',':','-.',':','-.','-','--',':','-.']
    markers=['None','None','None','None','+','x','.','x','^','v','<','>']
    
    ax.yaxis.set_major_locator(ScaledLocator(dx=yscale))
    ax.yaxis.set_major_formatter(ScaledFormatter(dx=yscale))
    ax.axis["right"].set_visible(False)
    ax.axis["top"].set_visible(False)
    
    if (level == 'node1'):
        legend_string = 'Node ' + timediff_nodes[0]
        ax.plot(xdata, ydata, linestyle=linestyles[0], color=colors[0],label=legend_string,clip_on=False)
        
    elif (level == 'node2'):
        legend_string = 'Node ' + timediff_nodes[1]
        ax.plot(xdata, ydata, linestyle=linestyles[1], color=colors[0],label=legend_string,clip_on=False)
        
    elif (level == 'node3'):
        legend_string = 'Node ' + timediff_nodes[2]
        ax.plot(xdata, ydata, linestyle=linestyles[2], color=colors[0],label=legend_string,clip_on=False)
        
    ax.legend(loc = "upper right")
    if (use_grid):
        ax.grid(use_grid)
    ax.set_xlabel('Run Number',{'fontsize':'x-large'})
    ax.set_ylabel('Time offset in ms',{'fontsize':'x-large'})
    
    ax.hold(True)
    if fig not in figures:
        figures.append(fig)  
  

def print_plot_linkqual(figures,fig,ax,xdata, ydata,use_grid,node, neighnode,avg=False,database_name=None):
 
    colors=['red','blue']
    linestyles=['None','-']
    markers=['.','None']
    ax.axis["right"].set_visible(False)
    ax.axis["top"].set_visible(False)
 
    pos = 0
    if avg:
        pos = 1

    if avg:
        legend_string = 'Moving Average'
#        legend_string = 'Link ' + node + ' - ' + neighnode
    else:
        if database_name != None:
            legend_string = database_name.split('_')[-1] + ' dB'
        else:
            legend_string = 'Link ' + node + ' - ' + neighnode
    ax.plot(xdata, ydata, linestyle=linestyles[pos], color=colors[pos],marker = markers[pos],label=legend_string,clip_on=False)

    ax.legend(loc = "lower right")
#    ax.legend(loc = "upper left")
    if (use_grid):
        ax.grid(use_grid)
    ax.set_xlabel('Run Number',{'fontsize':'x-large'})
    ax.set_ylabel('Link Quality',{'fontsize':'x-large'})
    ax.set_ylim([0,1])
  #  ax.set_xlim([0,300])
    ax.hold(True)
    if fig not in figures:
        figures.append(fig)  


class ScaledLocator(mpl.ticker.MaxNLocator):
    """
    Locates regular intervals along an axis scaled by *dx* and shifted by
    *x0*. For example, this would locate minutes on an axis plotted in seconds
    if dx=60.  This differs from MultipleLocator in that an approriate interval
    of dx units will be chosen similar to the default MaxNLocator.
    """
    def __init__(self, dx=1.0, x0=0.0):
        self.dx = dx
        self.x0 = x0
        mpl.ticker.MaxNLocator.__init__(self, nbins=9, steps=[1, 2, 5, 10])

    def rescale(self, x):
        return x / self.dx + self.x0
    def inv_rescale(self, x):
        return  (x - self.x0) * self.dx

    def __call__(self): 
        vmin, vmax = self.axis.get_view_interval()
        vmin, vmax = self.rescale(vmin), self.rescale(vmax)
        vmin, vmax = mpl.transforms.nonsingular(vmin, vmax, expander = 0.05)
        locs = self.bin_boundaries(vmin, vmax)
        locs = self.inv_rescale(locs)
        prune = self._prune
        if prune=='lower':
            locs = locs[1:]
        elif prune=='upper':
            locs = locs[:-1]
        elif prune=='both':
            locs = locs[1:-1]
        return self.raise_if_exceeds(locs)

class ScaledFormatter(mpl.ticker.OldScalarFormatter):
    """Formats tick labels scaled by *dx* and shifted by *x0*."""
    def __init__(self, dx=1.0, x0=0.0, **kwargs):
        self.dx, self.x0 = dx, x0

    def rescale(self, x):
        return x / self.dx + self.x0

    def __call__(self, x, pos=None):
        xmin, xmax = self.axis.get_view_interval()
        xmin, xmax = self.rescale(xmin), self.rescale(xmax)
        d = abs(xmax - xmin)
        x = self.rescale(x)
        s = self.pprint_val(x, d)
        return s
        
def get_value_at_time(x,deadline):
	pos = len(x) -1
	for p,num in enumerate(x):
		if (num >= deadline):
			pos = p
			break
	return pos


class fig_placeHolders:
	
	def __init__(self):		
		self._figs = defaultdict(dict)
		self._axs  = defaultdict(dict)
		params = {'legend.fontsize': 9,
          'legend.linewidth': 2,
          'xlabel.fontsize':'x-large',
          'ylabel.fontsize':'x-large',
          'grid.linewidth': 0.2,
          'grid.alpha': 0.7,
          }
		plt.rcParams.update(params)
					
	def add_figs(self,identifier1,identifier2,identifier3):
		for id1 in identifier1:
			for id2 in identifier2:
				if id2 not in self._figs[id1].keys():
					self._figs[id1].update({id2:{}})
					self._axs[id1].update({id2:{}})
				for id3 in identifier3: 
					if id3 not in self._figs[id1][id2].keys():
						self._figs[id1][id2].update({id3:plt.figure()})
						self._axs[id1][id2].update({id3:Subplot(self._figs[id1][id2][id3],111)})
						self._figs[id1][id2][id3].add_subplot(self._axs[id1][id2][id3])
					
	def get_fig_ax(self,identifier1,identifier2,identifier3):
		return (self._figs[identifier1][identifier2][identifier3],self._axs[identifier1][identifier2][identifier3])
		
	def get_figs_axs(self):
		return (self._figs,self._axs)
		
	def exist(self,identifier1,identifier2,identifier3):
		if identifier1 in self._figs.keys():
			if identifier2 in self._figs[identifier1].keys():
				if identifier3 in self._figs[identifier1][identifier2].keys():
					return True
				else:
					return False
			else:
				return False
		else:
			return False

def safe_figure(figures,savename):
    pp= PdfPages(savename)
    for fig in figures:
        pp.savefig(fig, dpi=600,bbox_inches='tight')
    pp.close()
