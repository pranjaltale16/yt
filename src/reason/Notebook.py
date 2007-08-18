from yt.reason import *

class PlotPanel(wx.Panel):
    def __init__(self, *args, **kwds):
        # begin wxGlade: ReasonVMPlotFrame.__init__
        self.parent = kwds["parent"]
        self.CurrentlyResizing = False
        wx.Panel.__init__(self, *args, **kwds)
        self.LinkPlots = True

        self._AUI_NOTEBOOK = wx.NewId()
        self.nb = wx.aui.AuiNotebook(self, self._AUI_NOTEBOOK)
        welcomeMessage = wx.StaticText(self.nb, -1, "Welcome to Reason!")
        self.nb.AddPage(welcomeMessage, "Welcome")

        # Good thing the aui module breaks naming convention
        self.nb.Bind(wx.aui.EVT_AUINOTEBOOK_PAGE_CHANGED,
                     self.UpdateSubscriptions)

        #self.vmPanel = vmtype(outputfile, self.statusBar, self.PlotPanel, -1, 
                                       #field=field, axis=axis)
        
        self.__set_properties()
        self.__do_layout()

    def UpdateSubscriptions(self, event):
        Publisher().unsubAll(("viewchange"))
        page = self.nb.GetPage(event.Selection)
        if not hasattr(page,'outputfile'): return
        cti = page.outputfile["CurrentTimeIdentifier"]
        toSubscribe = []
        if self.LinkPlots: 
            for i,p in [(i, self.nb.GetPage(i)) for i in range(self.nb.GetPageCount())]:
                try:
                    of = p.outputfile
                    if of["CurrentTimeIdentifier"] == cti: toSubscribe.append(p)
                except:
                    pass
        else: toSubscribe.append(page)
        for p in toSubscribe:
            Publisher().subscribe(self.MessageLogger)
            Publisher().subscribe(p.ChangeWidthFromMessage, ('viewchange','width'))
            Publisher().subscribe(p.ChangeFieldFromMessage, ('viewchange','field'))
            Publisher().subscribe(p.ChangeLimitsFromMessage, ('viewchange','limits'))
            Publisher().subscribe(p.ChangeCenterFromMessage, ('viewchange','center'))
            Publisher().subscribe(p.ChangeColorMapFromMessage, ('viewchange','cmap'))
        page.UpdateCanvas()

    def MessageLogger(self, message):
        print message

    def __set_properties(self):
        pass

    def __do_layout(self):
        PlotPanelSizer = wx.BoxSizer(wx.VERTICAL)
        PlotPanelSizer.Add(self.nb, 1, wx.EXPAND)
        self.SetSizer(PlotPanelSizer)
        self.Layout()

    def viewPF(self, event=None):
        r = ReasonParameterFileViewer(self, -1, outputfile=self.outputfile)
        r.Show()

    def OnSize(self, event):
        if self.CurrentlyResizing == True:
            return
        self.CurrentlyResizing = True
        #w,h = self.GetEffectiveMinSize()
        w,h = event.GetSize()
        xx = min(w,h)
        self.SetSize((xx,xx))
        w,h = self.vmPanel.GetClientSize()
        xx = min(w,h)
        xy = xx / self.vmPanel.figure.get_dpi()
        self.vmPanel.figure.set_size_inches(xy,xy)
        self.vmPanel.figure_canvas.SetSize((xx,xx))
        self.vmPanel.plot.redraw_image()
        self.Layout()
        self.CurrentlyResizing = False

    # For the following, we need to figure out which windows to apply the
    # action to before we apply it.
    # This is probably best accomplished through pubsub.

    def AddPlot(self, page, title, ID):
        self.nb.AddPage(page, title)
        # Now we subscribe to events with this ID

    def GetCurrentOutput(self):
        return self.nb.GetPage(self.nb.Selection).outputfile

    def OnCallSwitchField(self, event):
        self.nb.GetPage(self.nb.Selection).switch_field(event)

    def OnCallSetWidth(self, event):
        self.nb.GetPage(self.nb.Selection).set_width(event)

    def OnCallRedraw(self, event):
        self.nb.GetPage(self.nb.Selection).UpdateCanvas()

    def OnCallZoomTop(self, event):
        self.nb.GetPage(self.nb.Selection).fulldomain(event)

    def OnCallSetZLim(self, event):
        self.nb.GetPage(self.nb.Selection).set_zlim(event)

    def OnCallViewPF(self, event):
        of = self.GetCurrentOutput()

class VMPlotPage(wx.Panel):
    def __init__(self, parent, statusBar, outputfile, axis, field="Density", mw=None):
        wx.Panel.__init__(self, parent)

        self.parent = parent
        self.mw = mw

        self.AmDrawingCircle = False

        self.outputfile = outputfile
        self.figure = be.matplotlib.figure.Figure((4,4))
        self.axes = self.figure.add_subplot(111)
        self.statusBar = statusBar
        self.field = field
        self.circles = []

        self.SetBackgroundColour(wx.NamedColor("WHITE"))

        #self.center = outputfile.hierarchy.findMax("Density")[1]#[0.5,0.5,0.5]
        self.center = [0.5, 0.5, 0.5]
        self.axis = axis

        self.makePlot()

        be.Initialize(canvas=FigureCanvas)
        self.figure_canvas = be.engineVals["canvas"](self, -1, self.figure)

        self.axes.set_xticks(())
        self.axes.set_yticks(())
        self.axes.set_ylabel("")
        self.axes.set_xlabel("")
        
        # Note that event is a MplEvent
        self.figure_canvas.mpl_connect('motion_notify_event', self.UpdateStatusBar)

        self.figure_canvas.Bind(wx.EVT_LEFT_UP, self.ClickProcess)
        self.figure_canvas.Bind(wx.EVT_CONTEXT_MENU, self.OnShowContextMenu)

        self.popupmenu = wx.Menu()
        self.cmapmenu = wx.Menu()
        self.popupmenu.AppendMenu(-1, "Color Map", self.cmapmenu)
        for cmap in be.matplotlib.cm.cmapnames:
            item = self.cmapmenu.AppendRadioItem(-1, cmap)
            self.Bind(wx.EVT_MENU, self.OnColorMapChoice, item)
        self.popupmenu.AppendSeparator()
        centerOnMax = self.popupmenu.Append(-1, "Center on max")
        centerHere = self.popupmenu.Append(-1, "Center here")
        self.popupmenu.AppendSeparator()
        fullDomain = self.popupmenu.Append(-1, "Zoom Top")

        self.Bind(wx.EVT_MENU, self.OnCenterOnMax, centerOnMax)
        self.Bind(wx.EVT_MENU, self.OnCenterHere, centerHere)
        self.Bind(wx.EVT_MENU, self.fulldomain, fullDomain)

        # Now we pre-select the current cmap
        ccmap_name = self.plot.colorbar.cmap.name
        self.cmapmenu.FindItemById(self.cmapmenu.FindItem(ccmap_name)).Check(True)

        self.widthSlider = wx.Slider(self, -1, wx.SL_HORIZONTAL | wx.SL_AUTOTICKS)
        self.vals = na.logspace(log10(25*outputfile.hierarchy.getSmallestDx()),0,201)
        self.widthSlider.SetRange(0, 200)
        self.widthSlider.SetTickFreq(1,1)
        self.widthSlider.SetValue(200)

        self.widthBox = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.widthBox.SetValue("1.0")

        self.choices = outputfile.units.keys()
        self.choices.sort()

        self.unitList = wx.Choice(self, choices=self.choices)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.figure_canvas, 1, wx.EXPAND)

        self.ControlSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.sizer.Add(self.ControlSizer, 0, wx.EXPAND)

        self.InputControl = wx.BoxSizer(wx.VERTICAL)
        self.InputControl.AddSpacer(10)
        self.InputControl.Add(self.widthBox, 0, 0, 0)
        self.InputControl.AddSpacer(10)
        self.InputControl.Add(self.unitList, 0, wx.EXPAND, 0)
        self.InputControl.AddSpacer(10)

        self.ControlSizer.AddSpacer(10)
        self.ControlSizer.Add(self.InputControl, 0, 0, 0)
        self.ControlSizer.AddSpacer(10)
        self.SliderSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SliderSizer.Add(self.widthSlider, 1,  wx.ALIGN_CENTER, 0)
        self.ControlSizer.Add(self.SliderSizer, 1, wx.GROW | wx.ALIGN_CENTER, 0)
        self.ControlSizer.AddSpacer(10)

        self.SetSizer(self.sizer)
        self.Fit()

        self.unitList.Bind(wx.EVT_CHOICE, self.UpdateUnit)
        self.widthSlider.Bind(wx.EVT_SCROLL, self.UpdateTextFromScrollEvent)
        self.widthSlider.Bind(wx.EVT_SCROLL_THUMBRELEASE, self.UpdateWidth)
        self.widthBox.Bind(wx.EVT_TEXT_ENTER, self.UpdateWidthFromText)

    def OnCenterOnMax(self, event):
        v, c = self.outputfile.h.findMax("Density")
        Publisher().sendMessage(('viewchange','center'), c)

    def OnCenterHere(self, event):
        xp, yp = self.ContextMenuPosition
        x, y = self.ConvertPositionToDataPosition(xp, yp)
        print "CENTER HERE:", xp, yp, x, y
        if x == None or y == None: return
        self.ChangeCenter(x,y)

    def OnShowContextMenu(self, event):
        pos = event.GetPosition()
        pos = self.figure_canvas.ScreenToClient(pos)
        self.ContextMenuPosition = pos
        self.figure_canvas.PopupMenu(self.popupmenu, pos)

    def OnColorMapChoice(self, event):
        item = self.cmapmenu.FindItemById(event.GetId())
        text = item.GetText()
        Publisher().sendMessage(("viewchange","cmap"),text)

    def ChangeColorMapFromMessage(self, message):
        cmap = message.data
        self.plot.set_cmap(cmap)
        self.UpdateWidth()

    def ChangeCenterFromMessage(self, message):
        #print "Hey, got message", message
        x, y, z = message.data
        # We are dealing with a pass-by-reference center
        self.center[0] = x
        self.center[1] = y
        self.center[2] = z
        self.data.reslice(self.center[self.axis])
        # If we do this, we get 3x as many updates as we want
        #self.UpdateWidth()

    def ConvertPositionToDataPosition(self, xp, yp):
        print "CONVERT", xp, yp
        #if not self.figure.axes[0].in_axes(xp,yp): return None, None
        #xp, yp = self.figure.axes[0].transData.inverse_xy_tup((xp,yp)) 
        #print xp, yp
        dx = (self.plot.xlim[1] - self.plot.xlim[0])/self.plot.pix[0]
        dy = (self.plot.ylim[1] - self.plot.ylim[0])/self.plot.pix[1]
        l, b, width, height = self.figure.axes[0].bbox.get_bounds()
        x = (dx * (xp-l)) + self.plot.xlim[0]
        y = (dy * (yp-b)) + self.plot.ylim[0]
        print x, y
        return x, y

    def ChangeCenter(self, x, y):
        newCenter = self.center[:]
        newCenter[yt.lagos.x_dict[self.axis]] = x
        newCenter[yt.lagos.y_dict[self.axis]] = y
        Publisher().sendMessage(('viewchange','center'), tuple(newCenter))
        self.UpdateWidth()

    def ClickProcess(self, event):
        xp, yp = event.X, event.Y
        if event.AltDown():
            x,y = self.ConvertPositionToDataPosition(xp, yp)
            self.ChangeCenter(x, y)
        elif event.ShiftDown():
            if self.AmDrawingCircle:
                dx = (self.plot.xlim[1] - self.plot.xlim[0])/self.plot.pix[0]
                dy = (self.plot.ylim[1] - self.plot.ylim[0])/self.plot.pix[1]
                dc=wx.ClientDC(self.figure_canvas)
                b=dc.GetBrush()
                b.SetStyle(wx.TRANSPARENT)
                dc.SetBrush(b)
                rp = sqrt((xp-self.x1)**2.0 + \
                          (yp-self.y1)**2.0)
                r = sqrt(((xp-self.x1)*dx)**2.0 + \
                         ((yp-self.y1)*dy)**2.0)
                dc.DrawCircle(self.x1,self.y1,rp)
                unitname = self.choices[self.unitList.GetSelection()]
                unit = self.outputfile[unitname]
                cc = self.center[:]
                xd,yd = self.ConvertPositionToDataPosition(self.x1, self.y1)
                cc[lagos.x_dict[self.axis]] = xd
                cc[lagos.y_dict[self.axis]] = yd
                print "R: %0.5e %s (%0.9e, %0.9e, %0.9e)" % (r*unit, unitname,
                    cc[0], cc[1], cc[2])
                print cc, r
                sphere = self.outputfile.hierarchy.sphere( \
                    cc, r, fields = ["Density"])
                self.mw.AddSphere("Sphere: %0.3e %s" \
                        % (r*unit, unitname), sphere)
                self.AmDrawingCircle = False
            else:
                self.x1 = xp
                self.y1 = yp
                self.AmDrawingCircle = True

    def ChangeWidthFromMessage(self, message):
        w,u=message.data
        # Now we need to update the text, units and bar
        wI = self.unitList.GetItems().index(u)
        self.unitList.SetSelection(wI)
        self.widthBox.SetValue("%0.5e" % (w))
        val = w/self.outputfile[u]
        dx = (log10(self.vals[0])-log10(self.vals[-1]))/201
        self.widthSlider.SetValue(200-int(log10(val)/dx))
        self.ChangeWidth(w,u)

    def ChangeWidth(self, width, unit):
        self.plot.set_width(width, unit)
        self.UpdateCanvas()

    def UpdateUnit(self, event):
        pos = self.widthSlider.GetValue()
        self.UpdateTextFromScroll(pos)

    def UpdateTextFromScrollEvent(self, event):
        self.UpdateTextFromScroll(event.GetPosition())

    def UpdateTextFromScroll(self, pos):
        unitname = self.choices[self.unitList.GetSelection()]
        unit = self.outputfile[unitname]
        val = self.vals[pos] * unit
        #print unit, val
        self.widthBox.SetValue("%0.5e" % (val))

    def UpdateWidthFromText(self, event):
        val = float(event.GetString())
        if val < 0:
            return
        unitname = self.choices[self.unitList.GetSelection()]
        unit = self.outputfile[unitname]
        # Now we figure out the closest slider tick
        dx = (log10(self.vals[0])-log10(self.vals[-1]))/201
        self.widthSlider.SetValue(200-int(log10(val)/dx))
        #print dx, val, log10(val)/dx, int(log10(val)/dx)
        Publisher().sendMessage(('viewchange','width'), (val,unitname))

    def UpdateWidth(self, pos = None):
        val = float(self.widthBox.GetValue())
        unitname = self.choices[self.unitList.GetSelection()]
        unit = self.outputfile[unitname]
        Publisher().sendMessage(('viewchange','width'), (val,unitname))

    def ChangeCursor(self, event):
        self.figure_canvas.SetCursor(wx.StockCursor(wx.CURSOR_BULLSEYE))

    def UpdateStatusBar(self, event):
        #print event.x, event.y
        if event.inaxes:
            xp, yp = event.xdata, event.ydata
            dx = abs(self.plot.xlim[0] - self.plot.xlim[1])/self.plot.pix[0]
            dy = abs(self.plot.ylim[0] - self.plot.ylim[1])/self.plot.pix[1]
            x = (dx * xp) + self.plot.xlim[0]
            y = (dy * yp) + self.plot.ylim[0]
            self.statusBar.SetStatusText("x = %0.12e" % (x), 0)
            self.statusBar.SetStatusText("y = %0.12e" % (y), 1)
            self.statusBar.SetStatusText("v = %0.12e" % \
                                        (self.GetDataValue(xp,yp)), 2)

    def GetDataValue(self, x, y):
        return self.plot.image._A[int(y), int(x)]

    def fulldomain(self, *args):
        self.ChangeWidth(1,'1')
        Publisher().sendMessage(('viewchange','width'), (1,'1'))

    def set_width(self, *args):
        w, u = Toolbars.ChooseWidth(self.outputfile)
        self.ChangeWidth(w,u)
        Publisher().sendMessage(('viewchange','width'), (w,u))

    def set_zlim(self, *args):
        zmin, zmax = Toolbars.ChooseLimits(self.plot)
        self.ChangeLimits(zmin, zmax)
        Publisher().sendMessage(("viewchange","limits"),(zmin,zmax))

    def ChangeLimits(self, zmin, zmax):
        self.plot.set_zlim(zmin,zmax)
        self.UpdateCanvas()

    def ChangeLimitsFromMessage(self, message):
        zmin, zmax = message.data
        self.ChangeLimits(zmin,zmax)

    def redraw(self, *args):
        self.UpdateCanvas()

    def ChangeFieldFromMessage(self, message):
        field = message.data
        self.ChangeField(field)

    def ChangeField(self, field):
        self.plot.switch_z(field)
        self.UpdateCanvas()

    def switch_field(self, *args):
        field = Toolbars.ChooseField(self.outputfile)
        self.ChangeField(field)
        Publisher().sendMessage(('viewchange','field'), field)

    def UpdateCanvas(self, *args):
        if self.IsShown():
            self.figure_canvas.draw()
        #else: print "Opting not to update canvas"

    def SaveImage(self):
        print "Generating prefix"
        self.plot.generatePrefix('Plot')
        print "Got",self.plot.prefix
        wildcard = "PNG (*png)|*.png"
        dlg = wx.FileDialog( \
            self, message="Save Image As ...", defaultDir=os.getcwd(), \
            defaultFile=self.plot.prefix, wildcard=wildcard, style=wx.SAVE)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            print "Hey, setting up the damn canvas"
            canvas = self.figure_canvas.switch_backends(FigureCanvasAgg)
            canvas.print_figure(path,format="png")
        dlg.Destroy()
        

class SlicePlotPage(VMPlotPage):
    def makePlot(self):
        self.data = self.outputfile.hierarchy.slice(self.axis, 
                                    self.center[self.axis], self.field, self.center)
        self.plot = be.SlicePlot(self.data, self.field, figure=self.figure, axes=self.axes)
        
class ProjPlotPage(VMPlotPage):
    def makePlot(self):
        self.data = self.outputfile.hierarchy.proj(self.axis, 
                                   self.field, weightField=None, center=self.center)
        self.plot = be.ProjectionPlot(self.data, self.field, figure=self.figure, axes=self.axes)

    def ChangeCenterFromMessage(self, message):
        x, y, z = message.data
        # We are dealing with a pass-by-reference center
        self.center[0] = x
        self.center[1] = y
        self.center[2] = z
        #self.UpdateWidth()

class PhasePlotPage(wx.Panel):
    def __init__(self, parent, statusBar, dataObject, mw=None):
        wx.Panel.__init__(self, parent)
        self.parent = parent
        self.mw = mw
        
        self.figure = be.matplotlib.figure.Figure((4,4))
        self.axes = self.figure.add_subplot(111)
        self.statusBar = statusBar

        be.Initialize(canvas=FigureCanvas)
        self.figure_canvas = be.engineVals["canvas"](self, -1, self.figure)

class ReasonFidoSelector(wx.Frame):
    def __init__(self, *args, **kwds):
        # begin wxGlade: ReasonFidoSelector.__init__
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        wx.Frame.__init__(self, *args, **kwds)
        self.panel_4 = wx.Panel(self, -1)
        self.panel_5 = wx.Panel(self.panel_4, -1)
        self.FidoOutputs = wx.TreeCtrl(self.panel_4, -1, style=wx.TR_HAS_BUTTONS|wx.TR_DEFAULT_STYLE|wx.SUNKEN_BORDER)
        self.label_1 = wx.StaticText(self.panel_5, -1, "label_1")

        self.__set_properties()
        self.__do_layout()
        # end wxGlade

    def __set_properties(self):
        pass
        # begin wxGlade: ReasonFidoSelector.__set_properties
        self.SetTitle("frame_4")
        # end wxGlade

    def __do_layout(self):
        # begin wxGlade: ReasonFidoSelector.__do_layout
        sizer_5 = wx.BoxSizer(wx.VERTICAL)
        sizer_6 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_7 = wx.BoxSizer(wx.HORIZONTAL)
        sizer_6.Add(self.FidoOutputs, 1, wx.EXPAND, 0)
        sizer_7.Add(self.label_1, 0, 0, 0)
        self.panel_5.SetSizer(sizer_7)
        sizer_6.Add(self.panel_5, 1, wx.EXPAND, 0)
        self.panel_4.SetSizer(sizer_6)
        sizer_5.Add(self.panel_4, 1, wx.EXPAND, 0)
        self.SetSizer(sizer_5)
        sizer_5.Fit(self)
        self.Layout()

class ReasonParameterFileViewer(wx.Frame):
    def __init__(self, *args, **kwds):
        kwds["style"] = wx.DEFAULT_FRAME_STYLE
        kwds["title"] = "yt - Reason"
        kwds["size"] = (800,800)
        pf = kwds.pop("outputfile")
        wx.Frame.__init__(self, *args, **kwds)

        # Add the text ctrl
        self.pf = wx.TextCtrl(self, -1, style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL)
        self.pf.LoadFile(pf.parameterFilename)

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.pf, 1, wx.EXPAND, 0)
        self.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.Layout()
        self.SetSize((600,600))

class ReasonApp(wx.App):
    def OnInit(self):
        wx.InitAllImageHandlers()
        frame_1 = ReasonMainWindow(None, -1)
        self.SetTopWindow(frame_1)
        frame_1.Show()
        return True

if __name__ == "__main__":
    app = ReasonApp(0)
    app.MainLoop()
